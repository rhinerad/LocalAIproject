"""Reference integration layer. Requires requests; no GPU libraries in this process.

Source: docs/GVD_QA_IMPLEMENTATION_BLUEPRINT.md section 5.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol


class QAError(RuntimeError):
    """Infrastructure, malformed evidence, or uncertain judgment: do not reroll."""


class Rejected(RuntimeError):
    """Valid evaluations exhausted the configured generation budget."""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    last_error: OSError | None = None
    for _ in range(20):
        try:
            os.replace(temp, path)
            last_error = None
            break
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.05)
    if last_error is not None:
        raise last_error


def finite_number(value: Any, lo: float | None = None,
                  hi: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise QAError("Score is not a numeric scalar")
    try:
        number = float(value)
    except ValueError as e:
        raise QAError("Invalid score") from e
    if not math.isfinite(number):
        raise QAError("Non-finite score")
    if lo is not None and number < lo or hi is not None and number > hi:
        raise QAError("Score outside declared range")
    return number


def one_report(history: dict, node_id: str, key: str,
               attempt_id: str, image_sha256: str, profile_id: str) -> dict:
    try:
        rows = history["outputs"][node_id][key]
    except (KeyError, TypeError) as e:
        raise QAError(f"Missing report at node {node_id}") from e
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise QAError("Expected exactly one image report")
    report = rows[0]
    expected = {"schema_version": 1, "attempt_id": attempt_id,
                "image_sha256": image_sha256, "profile_id": profile_id}
    if any(report.get(k) != v for k, v in expected.items()):
        raise QAError("Stale or mismatched QA evidence")
    return report


@dataclass(frozen=True)
class Policy:
    # Supply calibrated values explicitly; there are no universal defaults.
    policy_id: str
    metrics_profile: str
    qwen_profile: str
    reward_profile: str
    clip_text_min: float
    required_ids: tuple[str, ...]
    clip_unit: str = "torchmetrics_clipscore_0_100"
    dino_min: float | None = None
    clip_image_min: float | None = None
    reward_min: float | None = None
    max_attempts: int = 4
    best_of_k: int | None = None
    crop_ids: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.clip_unit not in {"torchmetrics_clipscore_0_100", "raw_cosine"}:
            raise QAError("Unknown CLIP unit")
        bounds = (0, 100) if self.clip_unit == "torchmetrics_clipscore_0_100" else (-1, 1)
        finite_number(self.clip_text_min, *bounds)
        if self.reward_min is not None:
            finite_number(self.reward_min)
        for value in (self.dino_min, self.clip_image_min):
            if value is not None:
                finite_number(value, -1, 1)
        if not self.required_ids or len(set(self.required_ids)) != len(self.required_ids):
            raise QAError("Requirement IDs must be nonempty and unique")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 16:
            raise QAError("Invalid attempt budget")
        if self.best_of_k is not None:
            if type(self.best_of_k) is not int or not 2 <= self.best_of_k <= 16:
                raise QAError("best_of_k must be an integer from 2 to 16")
            if self.best_of_k > self.max_attempts:
                raise QAError("best_of_k cannot exceed max_attempts")


def evaluate_fast(history: dict, attempt: str, digest: str,
                  policy: Policy, node_id: str = "90") -> tuple[dict, list[str]]:
    r = one_report(history, node_id, "gvd_metrics", attempt, digest,
                   policy.metrics_profile)
    if r.get("clip_text_unit") != policy.clip_unit:
        raise QAError("CLIP unit mismatch")
    bounds = (0, 100) if policy.clip_unit == "torchmetrics_clipscore_0_100" else (-1, 1)
    scores = {"clip_text": finite_number(r.get("clip_text"), *bounds)}
    reasons = []
    if scores["clip_text"] < policy.clip_text_min:
        reasons.append("clip_text_below_threshold")
    for field, threshold in (("dino", policy.dino_min),
                             ("clip_image", policy.clip_image_min)):
        raw = r.get(field)
        if raw is not None:
            scores[field] = finite_number(raw, -1, 1)
        if threshold is not None:
            if field not in scores:
                raise QAError(f"Required metric missing: {field}")
            if scores[field] < threshold:
                reasons.append(field + "_below_threshold")
    return scores, reasons


def evaluate_qwen(history: dict, attempt: str, digest: str,
                  policy: Policy, requirements_sha256: str,
                  node_id: str = "91") -> list[str]:
    r = one_report(history, node_id, "gvd_qa", attempt, digest, policy.qwen_profile)
    if r.get("requirements_sha256") != requirements_sha256:
        raise QAError("Rubric changed or report is stale")
    checks = r.get("checks")
    if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
        raise QAError("Malformed Qwen checks")
    ids = [c.get("id") for c in checks]
    if len(ids) != len(policy.required_ids) or set(ids) != set(policy.required_ids):
        raise QAError("Missing, duplicate, or extra Qwen checks")
    if any(c.get("verdict") not in {"pass", "fail", "unknown"} for c in checks):
        raise QAError("Invalid Qwen verdict")
    if any(c["verdict"] == "unknown" for c in checks):
        raise QAError("Uncertain visual evidence; block or recheck same image")
    computed = all(c["verdict"] == "pass" for c in checks)
    if type(r.get("qwen_pass")) is not bool or r["qwen_pass"] != computed:
        raise QAError("Invalid Boolean or inconsistent aggregate")
    return ["qwen:" + c["id"] for c in checks if c["verdict"] == "fail"]


def wd14_traits(history: dict, trait_aliases: dict[str, tuple[str, ...]],
                node_id: str = "30") -> dict:
    rows = history.get("outputs", {}).get(node_id, {}).get("tags")
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], str):
        raise QAError("Missing or batched WD14 evidence")
    normalize = lambda text: text.strip().lower().replace("_", " ")
    tags = {normalize(tag) for tag in rows[0].split(",") if tag.strip()}
    return {trait: {
        "status": "tag_supported" if tags.intersection(map(normalize, aliases)) else "not_detected",
        "matched_tags": sorted(tags.intersection(map(normalize, aliases)))
    } for trait, aliases in trait_aliases.items()}


class ComfyClient:
    def __init__(self, base_url: str):
        import requests
        self.base = base_url.rstrip("/")
        self.http = requests.Session()

    def run(self, graph: dict, attempt: str, journal: Path,
            timeout_s: float = 1800) -> dict:
        import requests
        # Caller uses a fresh journal path for every stage submission.
        if journal.exists():
            raise QAError("Existing submission journal: reconcile before retry")
        atomic_json(journal, {"state": "submitting", "attempt_id": attempt,
                              "graph": graph})
        try:
            response = self.http.post(self.base + "/prompt", json={
                "prompt": graph, "client_id": uuid.uuid4().hex,
                "extra_data": {"gvd_attempt_id": attempt}}, timeout=(5, 30))
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError) as e:
            # Server may have accepted the request. Never submit it again blindly.
            raise QAError("Submission unresolved; reconcile queue/history") from e
        if data.get("error") or data.get("node_errors") or not data.get("prompt_id"):
            raise QAError(f"ComfyUI rejected graph: {data}")
        prompt_id = data["prompt_id"]
        atomic_json(journal, {"state": "queued", "attempt_id": attempt,
                              "prompt_id": prompt_id, "graph": graph})
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            response = self.http.get(self.base + "/history/" + prompt_id,
                                     timeout=(5, 30))
            response.raise_for_status()
            item = response.json().get(prompt_id)
            if item:
                status = item.get("status", {})
                errors = {"execution_error", "execution_interrupted"}
                messages = status.get("messages", [])
                if status.get("status_str") == "error" or any(
                    isinstance(m, list) and m and m[0] in errors for m in messages
                ):
                    atomic_json(journal, {"state": "failed", "prompt_id": prompt_id,
                                          "history": item})
                    raise QAError("ComfyUI execution failed; not a quality rejection")
                if status.get("completed") is True and status.get("status_str") == "success":
                    atomic_json(journal, {"state": "completed", "prompt_id": prompt_id,
                                          "history": item})
                    return item
            time.sleep(0.5)
        raise QAError("Execution timed out; reconcile owned prompt before continuing")

    def image_bytes(self, history: dict, save_node: str) -> bytes:
        images = history.get("outputs", {}).get(save_node, {}).get("images", [])
        if len(images) != 1:
            raise QAError("Expected one generated candidate")
        ref = images[0]
        response = self.http.get(self.base + "/view", params={
            k: ref[k] for k in ("filename", "subfolder", "type")}, timeout=(5, 60))
        response.raise_for_status()
        return response.content

    def upload(self, image: bytes, digest: str) -> str:
        response = self.http.post(self.base + "/upload/image", files={
            "image": (digest + ".png", image, "image/png")},
            data={"overwrite": "false", "type": "input"}, timeout=(5, 60))
        response.raise_for_status()
        data = response.json()
        return "/".join(x for x in (data.get("subfolder", ""), data["name"]) if x)


class PhaseController(Protocol):
    # Mandatory local implementation: owns a machine-wide GPU lease,
    # checks idle queues, unloads/stops previous worker, admits target profile.
    # enter must raise on failure; it must never be implemented as a no-op.
    def enter(self, phase: str) -> ComfyClient: ...
    def idle(self) -> None: ...


def _orphan_candidate_folders(job_dir: Path) -> list[Path]:
    if not job_dir.exists():
        return []
    rows = []
    for child in sorted(job_dir.iterdir()):
        if child.is_dir() and (child / "candidate.png").is_file() and not (child / "verdict.json").is_file():
            rows.append(child)
    return rows


def score_saved_candidate(
    image: bytes,
    *,
    attempt: str,
    folder: Path,
    seed: int | None,
    policy: Policy,
    rubric_digest: str,
    make_fast_graph: Callable[[str, str, str], dict],
    make_qwen_graph: Callable[[str, str, str], dict],
    make_reward_graph: Callable[[str, str, str], dict],
    phases: PhaseController,
    wd14_aliases: dict[str, tuple[str, ...]] | None,
    record_evidence: Callable[..., None] | None,
    job_dir: Path,
    requirements_json: str,
) -> dict[str, Any]:
    digest = sha256(image)
    qwen_checks = None
    client = phases.enter("fast_qa")
    name = client.upload(image, digest)
    fast = client.run(make_fast_graph(name, attempt, digest), attempt, folder / "fast.json")
    scores, reasons = evaluate_fast(fast, attempt, digest, policy)
    traits = wd14_traits(fast, wd14_aliases) if wd14_aliases else {}
    if not reasons:
        client = phases.enter("qwen_qa")
        name = client.upload(image, digest)
        qwen = client.run(make_qwen_graph(name, attempt, digest), attempt, folder / "qwen.json")
        reasons = evaluate_qwen(qwen, attempt, digest, policy, rubric_digest)
        qwen_checks = one_report(qwen, "91", "gvd_qa", attempt, digest,
                                 policy.qwen_profile).get("checks")
    if not reasons:
        client = phases.enter("reward_qa")
        name = client.upload(image, digest)
        reward_history = client.run(make_reward_graph(name, attempt, digest),
                                   attempt, folder / "reward.json")
        reward = one_report(reward_history, "92", "gvd_reward", attempt,
                            digest, policy.reward_profile)
        if reward.get("unit") != "imagereward_raw":
            raise QAError("ImageReward unit mismatch")
        scores["image_reward"] = finite_number(reward.get("image_reward"))
        if policy.reward_min is not None and scores["image_reward"] < policy.reward_min:
            reasons.append("imagereward_below_threshold")
    verdict = {
        "attempt_id": attempt, "seed": seed, "image_sha256": digest,
        "policy_id": policy.policy_id, "scores": scores,
        "wd14_traits": traits, "qwen_checks": qwen_checks,
        "reasons": reasons, "accepted": not reasons,
        "image_path": str((folder / "candidate.png").resolve()),
    }
    atomic_json(folder / "verdict.json", verdict)
    if record_evidence is not None:
        record_evidence(job_dir=job_dir, verdict=verdict,
                        rubric_sha256=rubric_digest, prompt=requirements_json)
    return verdict


def generate_until_accepted(
    generation_graph: dict,
    seed_bindings: tuple[tuple[str, str], ...],
    generation_save_node: str,
    base_seed: int,
    expected_size: tuple[int, int],
    policy: Policy,
    requirements_json: str,
    make_fast_graph: Callable[[str, str, str], dict],
    make_qwen_graph: Callable[[str, str, str], dict],
    make_reward_graph: Callable[[str, str, str], dict],
    phases: PhaseController,
    job_dir: Path,
    wd14_aliases: dict[str, tuple[str, ...]] | None = None,
    resume: bool = False,
    record_evidence: Callable[..., None] | None = None,
) -> Path:
    """Call inside GVD's exclusive GPU lease. Returns only an acceptance receipt."""
    policy.validate()
    if type(base_seed) is not int or not 0 <= base_seed < 2**64:
        raise QAError("Invalid seed")
    requirements = json.loads(requirements_json)
    if sorted(c["id"] for c in requirements) != sorted(policy.required_ids):
        raise QAError("Policy and rubric disagree")
    rubric_digest = sha256(requirements_json.encode())
    if resume:
        existing = _resume_receipt(job_dir, policy.policy_id, rubric_digest)
        if existing is not None:
            return existing
        reconcile_job_dir(job_dir)
        job_dir.mkdir(parents=True, exist_ok=True)
        start_index = _next_attempt_index(job_dir, base_seed)
    else:
        job_dir.mkdir(parents=True, exist_ok=False)  # resume is explicit, never overwrite
        start_index = 0
    qualifiers: list[dict[str, Any]] = []
    score_kw = dict(
        policy=policy, rubric_digest=rubric_digest,
        make_fast_graph=make_fast_graph, make_qwen_graph=make_qwen_graph,
        make_reward_graph=make_reward_graph, phases=phases,
        wd14_aliases=wd14_aliases, record_evidence=record_evidence,
        job_dir=job_dir, requirements_json=requirements_json,
    )
    try:
        if resume:
            for orphan in _orphan_candidate_folders(job_dir):
                image = (orphan / "candidate.png").read_bytes()
                verdict = score_saved_candidate(
                    image, attempt=orphan.name, folder=orphan, seed=None, **score_kw)
                if not verdict["reasons"] and policy.best_of_k is None:
                    receipt = job_dir / "accepted.json"
                    atomic_json(receipt, {**verdict, "requirements_sha256": rubric_digest,
                                          "resumed_orphan": True})
                    return receipt
                if not verdict["reasons"]:
                    qualifiers.append(verdict)
        for index in range(start_index, policy.max_attempts):
            seed = (base_seed + index) % 2**64
            attempt = uuid.uuid4().hex
            folder = job_dir / attempt
            folder.mkdir()
            graph = copy.deepcopy(generation_graph)
            if not seed_bindings:
                raise QAError("No declared generation seed binding")
            for node, name in seed_bindings:
                if name not in graph[node]["inputs"]:
                    raise QAError("Seed binding does not exist")
                graph[node]["inputs"][name] = seed
            graph[generation_save_node]["inputs"]["filename_prefix"] = "gvd_candidates/" + attempt
            client = phases.enter("generate")
            history = client.run(graph, attempt, folder / "generation.json")
            image = client.image_bytes(history, generation_save_node)
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(image)) as decoded:
                if decoded.format != "PNG" or decoded.size != expected_size:
                    raise QAError("Candidate media differs from the shot contract")
                decoded.verify()
            digest = sha256(image)
            (folder / "candidate.png").write_bytes(image)
            verdict = score_saved_candidate(
                image, attempt=attempt, folder=folder, seed=seed, **score_kw)
            if verdict["reasons"]:
                continue  # quality failure only: next seed, unchanged rubric
            if policy.best_of_k is None:
                receipt = job_dir / "accepted.json"
                atomic_json(receipt, {**verdict, "requirements_sha256": rubric_digest})
                return receipt
            qualifiers.append(verdict)
        if policy.best_of_k is not None and qualifiers:
            winner = select_best_qualifier(qualifiers)
            receipt = job_dir / "accepted.json"
            atomic_json(receipt, {**winner, "requirements_sha256": rubric_digest,
                                  "selection": "best_of_k"})
            return receipt
        atomic_json(job_dir / "blocked.json", {"reason": "quality_budget_exhausted"})
        raise Rejected("No candidate passed; I2V remains blocked")
    finally:
        phases.idle()  # errors must still stop/unload owned verifier workers


def generate_wave_then_score(
    generation_graph: dict,
    seed_bindings: tuple[tuple[str, str], ...],
    generation_save_node: str,
    base_seed: int,
    expected_size: tuple[int, int],
    policy: Policy,
    requirements_json: str,
    make_fast_graph: Callable[[str, str, str], dict],
    make_qwen_graph: Callable[[str, str, str], dict],
    make_reward_graph: Callable[[str, str, str], dict],
    phases: PhaseController,
    job_dir: Path,
    wave_n: int,
    wd14_aliases: dict[str, tuple[str, ...]] | None = None,
    record_evidence: Callable[..., None] | None = None,
) -> Path:
    """Generate a wave under one diffusion residency, release, then score each PNG."""
    policy.validate()
    if type(wave_n) is not int or wave_n < 1 or wave_n > policy.max_attempts:
        raise QAError("wave_n must be between 1 and max_attempts")
    requirements = json.loads(requirements_json)
    if sorted(c["id"] for c in requirements) != sorted(policy.required_ids):
        raise QAError("Policy and rubric disagree")
    rubric_digest = sha256(requirements_json.encode())
    job_dir.mkdir(parents=True, exist_ok=False)
    score_kw = dict(
        policy=policy, rubric_digest=rubric_digest,
        make_fast_graph=make_fast_graph, make_qwen_graph=make_qwen_graph,
        make_reward_graph=make_reward_graph, phases=phases,
        wd14_aliases=wd14_aliases, record_evidence=record_evidence,
        job_dir=job_dir, requirements_json=requirements_json,
    )
    saved: list[tuple[Path, bytes, int, str]] = []
    qualifiers: list[dict[str, Any]] = []
    try:
        client = phases.enter("generate")
        for index in range(wave_n):
            seed = (base_seed + index) % 2**64
            attempt = uuid.uuid4().hex
            folder = job_dir / attempt
            folder.mkdir()
            graph = copy.deepcopy(generation_graph)
            for node, name in seed_bindings:
                graph[node]["inputs"][name] = seed
            graph[generation_save_node]["inputs"]["filename_prefix"] = "gvd_candidates/" + attempt
            history = client.run(graph, attempt, folder / "generation.json")
            image = client.image_bytes(history, generation_save_node)
            from io import BytesIO
            from PIL import Image
            with Image.open(BytesIO(image)) as decoded:
                if decoded.format != "PNG" or decoded.size != expected_size:
                    raise QAError("Candidate media differs from the shot contract")
                decoded.verify()
            (folder / "candidate.png").write_bytes(image)
            saved.append((folder, image, seed, attempt))
        phases.idle()
        for folder, image, seed, attempt in saved:
            verdict = score_saved_candidate(
                image, attempt=attempt, folder=folder, seed=seed, **score_kw)
            if verdict["reasons"]:
                continue
            if policy.best_of_k is None:
                receipt = job_dir / "accepted.json"
                atomic_json(receipt, {**verdict, "requirements_sha256": rubric_digest,
                                      "mode": "wave"})
                return receipt
            qualifiers.append(verdict)
        if policy.best_of_k is not None and qualifiers:
            winner = select_best_qualifier(qualifiers)
            receipt = job_dir / "accepted.json"
            atomic_json(receipt, {**winner, "requirements_sha256": rubric_digest,
                                  "selection": "best_of_k", "mode": "wave"})
            return receipt
        atomic_json(job_dir / "blocked.json", {"reason": "quality_budget_exhausted"})
        raise Rejected("No candidate passed; I2V remains blocked")
    finally:
        phases.idle()


def evaluate_persisted_candidate(
    image: bytes,
    *,
    policy: Policy,
    requirements_json: str,
    make_fast_graph: Callable[[str, str, str], dict],
    make_qwen_graph: Callable[[str, str, str], dict],
    make_reward_graph: Callable[[str, str, str], dict],
    phases: PhaseController,
    job_dir: Path,
    wd14_aliases: dict[str, tuple[str, ...]] | None = None,
    record_evidence: Callable[..., None] | None = None,
    expected_size: tuple[int, int] | None = None,
    attempt_id: str | None = None,
) -> Path:
    """Score one saved PNG. Does not generate or reroll seeds."""
    policy.validate()
    requirements = json.loads(requirements_json)
    if sorted(c["id"] for c in requirements) != sorted(policy.required_ids):
        raise QAError("Policy and rubric disagree")
    rubric_digest = sha256(requirements_json.encode())
    job_dir.mkdir(parents=True, exist_ok=False)
    attempt = attempt_id or uuid.uuid4().hex
    folder = job_dir / attempt
    folder.mkdir()
    from io import BytesIO
    from PIL import Image
    with Image.open(BytesIO(image)) as decoded:
        if decoded.format != "PNG":
            raise QAError("Candidate media differs from the shot contract")
        size = decoded.size
        if expected_size is not None and size != expected_size:
            raise QAError("Candidate media differs from the shot contract")
        decoded.verify()
    digest = sha256(image)
    (folder / "candidate.png").write_bytes(image)
    qwen_checks: list[Any] | None = None
    try:
        client = phases.enter("fast_qa")
        name = client.upload(image, digest)
        fast = client.run(make_fast_graph(name, attempt, digest), attempt,
                          folder / "fast.json")
        scores, reasons = evaluate_fast(fast, attempt, digest, policy)
        traits = wd14_traits(fast, wd14_aliases) if wd14_aliases else {}
        if not reasons:
            client = phases.enter("qwen_qa")
            name = client.upload(image, digest)
            qwen = client.run(make_qwen_graph(name, attempt, digest), attempt,
                              folder / "qwen.json")
            reasons = evaluate_qwen(qwen, attempt, digest, policy, rubric_digest)
            qwen_checks = one_report(qwen, "91", "gvd_qa", attempt, digest,
                                     policy.qwen_profile).get("checks")
        if not reasons:
            client = phases.enter("reward_qa")
            name = client.upload(image, digest)
            reward_history = client.run(make_reward_graph(name, attempt, digest),
                attempt, folder / "reward.json")
            reward = one_report(reward_history, "92", "gvd_reward", attempt,
                                digest, policy.reward_profile)
            if reward.get("unit") != "imagereward_raw":
                raise QAError("ImageReward unit mismatch")
            scores["image_reward"] = finite_number(reward.get("image_reward"))
            if policy.reward_min is not None and scores["image_reward"] < policy.reward_min:
                reasons.append("imagereward_below_threshold")
        verdict = {
            "attempt_id": attempt, "seed": None, "image_sha256": digest,
            "policy_id": policy.policy_id, "scores": scores,
            "wd14_traits": traits, "qwen_checks": qwen_checks,
            "reasons": reasons, "accepted": not reasons,
            "image_path": str((folder / "candidate.png").resolve()),
            "requirements_sha256": rubric_digest,
            "mode": "persisted_candidate",
        }
        atomic_json(folder / "verdict.json", verdict)
        if record_evidence is not None:
            record_evidence(job_dir=job_dir, verdict=verdict,
                            rubric_sha256=rubric_digest, prompt=requirements_json)
        dest = job_dir / ("accepted.json" if not reasons else "blocked.json")
        atomic_json(dest, verdict)
        return dest
    finally:
        phases.idle()


def accepted_i2v_image(receipt_path: Path, expected_policy: str,
                       expected_requirements_sha256: str) -> Path:
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QAError("I2V blocked: acceptance receipt is missing") from exc
    except json.JSONDecodeError as exc:
        raise QAError("I2V blocked: acceptance receipt is malformed") from exc
    if receipt.get("accepted") is not True or receipt.get("reasons") != []:
        raise QAError("Image lacks an acceptance decision")
    if receipt.get("policy_id") != expected_policy or receipt.get(
            "requirements_sha256") != expected_requirements_sha256:
        raise QAError("Acceptance applies to a different policy or shot")
    path = Path(receipt["image_path"]).resolve()
    # Restrict receipts to trusted job directories in the calling application.
    if sha256(path.read_bytes()) != receipt.get("image_sha256"):
        raise QAError("Accepted image changed")
    return path


def _resume_receipt(job_dir: Path, policy_id: str, rubric_digest: str) -> Path | None:
    receipt = job_dir / "accepted.json"
    if not receipt.is_file():
        return None
    accepted_i2v_image(receipt, policy_id, rubric_digest)
    return receipt


def reconcile_job_dir(job_dir: Path) -> None:
    if not job_dir.exists():
        return
    for journal in job_dir.glob("*/*.json"):
        if journal.name not in {"generation.json", "fast.json", "qwen.json", "reward.json"}:
            continue
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise QAError(f"Corrupt stage journal {journal}") from exc
        if data.get("state") in {"submitting", "queued"}:
            raise QAError("Existing submission journal: reconcile before retry")


def _next_attempt_index(job_dir: Path, base_seed: int) -> int:
    used = 0
    for child in job_dir.iterdir():
        if child.is_dir() and (child / "verdict.json").is_file():
            used += 1
    return used


def select_best_qualifier(verdicts: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [v for v in verdicts if v.get("accepted") is True and v.get("reasons") == []]
    if not accepted:
        raise Rejected("No candidate passed; I2V remains blocked")
    def reward(row: dict[str, Any]) -> float:
        scores = row.get("scores") or {}
        value = scores.get("image_reward")
        return float(value) if isinstance(value, (int, float)) else float("-inf")
    return max(accepted, key=reward)


def redirect_generation_save(graph: dict, image_node: str, save_node: str = "9") -> dict:
    """Keep sampling; bind a private candidate SaveImage; drop ungated publish nodes."""
    out = copy.deepcopy(graph)
    drop = []
    for node_id, node in out.items():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type") or "")
        if cls in {"VHS_VideoCombine", "MiniMaxH3ImageToVideo", "SaveVideo"} and node_id != save_node:
            drop.append(node_id)
        if cls == "SaveImage" and node_id != save_node:
            drop.append(node_id)
    for node_id in drop:
        out.pop(node_id, None)
    out[save_node] = {
        "class_type": "SaveImage",
        "inputs": {
            "images": [str(image_node), 0],
            "filename_prefix": "gvd_candidates/ATTEMPT_ID",
        },
    }
    return out


def graph_class_types(graph: dict) -> set[str]:
    classes = set()
    for node in graph.values():
        if isinstance(node, dict) and node.get("class_type"):
            classes.add(str(node["class_type"]))
    return classes


def missing_graph_classes(graph: dict, object_info: dict | None) -> list[str]:
    if not isinstance(object_info, dict):
        raise QAError("object_info unavailable; cannot activate QA graphs")
    missing = []
    for cls in sorted(graph_class_types(graph)):
        if cls.startswith("CANDIDATE") or "ATTEMPT" in cls:
            continue
        if cls not in object_info:
            missing.append(cls)
    return missing


def clip_token_audit(text: str, *, limit: int = 77) -> dict[str, Any]:
    """Conservative whitespace count. Replace with the encoder tokenizer when pinned."""
    tokens = [part for part in str(text).split() if part]
    return {
        "approx_tokens": len(tokens),
        "limit": limit,
        "overlong": len(tokens) > limit,
        "text_sha256": sha256(str(text).encode()),
    }


def ablation_jobs(plan_history, seeds, model_profile, audit_rubric_hash):
    variants = plan_history["outputs"]["61"]["gvd_variants"]
    for variant in variants:
        for seed in seeds:
            yield {
                "variant_index": variant["index"],
                "variant_hash": sha256(variant["prompt"].encode()),
                "prompt": variant["prompt"],
                "seed": seed,
                "model_profile": model_profile,
                "rubric_sha256": audit_rubric_hash,
                "max_attempts": 1,
                "purpose": "ablation_measurement",
            }


def attach_subject_crop(graph: dict, *, image_node: str, crop: dict[str, int],
                        crop_id: str, node_id: str = "3") -> dict:
    """Record a crop box on LoadImage output. ImageCrop is used when the class exists later."""
    out = copy.deepcopy(graph)
    out[node_id] = {
        "class_type": "ImageCrop",
        "inputs": {
            "image": [str(image_node), 0],
            "x": int(crop["x"]),
            "y": int(crop["y"]),
            "width": int(crop["width"]),
            "height": int(crop["height"]),
        },
        "_meta": {"crop_id": crop_id},
    }
    return out


def onnx_must_be_cpu(providers: list[str] | tuple[str, ...]) -> None:
    lowered = [str(p) for p in providers]
    if any("CUDA" in p.upper() or "TENSORRT" in p.upper() or "DML" in p.upper() for p in lowered):
        raise QAError("WD14/ONNX GPU providers are forbidden in the CPU QA worker")
    if "CPUExecutionProvider" not in lowered:
        raise QAError("WD14/ONNX must list CPUExecutionProvider")


def policy_from_mapping(data: dict[str, Any]) -> Policy:
    required = data.get("required_ids") or ()
    return Policy(
        policy_id=str(data["policy_id"]),
        metrics_profile=str(data["metrics_profile"]),
        qwen_profile=str(data["qwen_profile"]),
        reward_profile=str(data["reward_profile"]),
        clip_text_min=float(data["clip_text_min"]),
        required_ids=tuple(required),
        clip_unit=str(data.get("clip_unit") or "torchmetrics_clipscore_0_100"),
        dino_min=data.get("dino_min"),
        clip_image_min=data.get("clip_image_min"),
        reward_min=data.get("reward_min"),
        max_attempts=int(data.get("max_attempts") or 4),
        best_of_k=data.get("best_of_k"),
        crop_ids=tuple(data.get("crop_ids") or ()),
    )


def bind_qa(template, filename, attempt_id, digest, report_node, profile_id):
    graph = copy.deepcopy(template)
    graph["1"]["inputs"]["image"] = filename
    graph[report_node]["inputs"].update(
        attempt_id=attempt_id, image_sha256=digest, profile_id=profile_id)
    return graph


def unload_owned_ollama(session, ollama_url, exact_owned_model):
    response = session.post(ollama_url + "/api/generate", json={
        "model": exact_owned_model, "prompt": "", "stream": False,
        "keep_alive": 0}, timeout=(5, 60))
    response.raise_for_status()


def free_idle_comfy(session, comfy_url):
    response = session.get(comfy_url + "/queue", timeout=(5, 15))
    response.raise_for_status()
    queue = response.json()
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise QAError("Worker is busy; memory transition is not allowed")
    response = session.post(comfy_url + "/free", json={
        "unload_models": True, "free_memory": True}, timeout=(5, 30))
    response.raise_for_status()
