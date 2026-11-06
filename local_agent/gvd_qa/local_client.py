"""Agent-side QA client. Same history shape as GVD* output nodes; no YRIKKA in Comfy."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import sys

ROOT = Path(__file__).resolve().parents[2]
import importlib.util
_SPEC = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
_RUNNER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
sys.modules.setdefault("_gvd_qa_runner", _RUNNER)
_SPEC.loader.exec_module(_RUNNER)

QAError = _RUNNER.QAError
atomic_json = _RUNNER.atomic_json
sha256 = _RUNNER.sha256

ClipFn = Callable[[bytes, str], float]
CheckFn = Callable[[bytes, list[dict[str, Any]]], list[dict[str, Any]]]
RewardFn = Callable[[bytes, str], float]
Wd14Fn = Callable[[bytes], str]
DinoFn = Callable[[bytes], float]


class LocalQaClient:
    """Implements ComfyClient.upload/run/image_bytes for isolated QA phases."""

    def __init__(
        self,
        *,
        clip_score_fn: ClipFn | None = None,
        checklist_fn: CheckFn | None = None,
        reward_fn: RewardFn | None = None,
        wd14_fn: Wd14Fn | None = None,
        dino_fn: DinoFn | None = None,
        clip_image_fn: DinoFn | None = None,
        clip_unit: str = "torchmetrics_clipscore_0_100",
        audit_caption: str = "",
        enforce_clip_token_limit: bool = True,
    ) -> None:
        self.images: dict[str, bytes] = {}
        self.clip_score_fn = clip_score_fn
        self.checklist_fn = checklist_fn
        self.reward_fn = reward_fn
        self.wd14_fn = wd14_fn
        self.dino_fn = dino_fn
        self.clip_image_fn = clip_image_fn
        self.clip_unit = clip_unit
        self.audit_caption = audit_caption
        self.enforce_clip_token_limit = enforce_clip_token_limit

    def upload(self, image: bytes, digest: str) -> str:
        name = digest + ".png"
        self.images[digest] = image
        self.images[name] = image
        return name

    def image_bytes(self, history: dict, save_node: str) -> bytes:
        raise QAError("LocalQaClient does not generate diffusion images")

    def run(self, graph: dict, attempt: str, journal: Path) -> dict:
        if journal.exists():
            raise QAError("Existing submission journal: reconcile before retry")
        atomic_json(journal, {"state": "submitting", "attempt_id": attempt, "graph": graph})
        classes = {
            nid: str(node.get("class_type") or "")
            for nid, node in graph.items() if isinstance(node, dict)
        }
        digest = None
        profile = None
        caption = self.audit_caption
        requirements_json = "[]"
        for node in graph.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs") or {}
            if inputs.get("image_sha256") and isinstance(inputs["image_sha256"], str):
                digest = inputs["image_sha256"]
            if inputs.get("profile_id") and isinstance(inputs["profile_id"], str):
                profile = inputs["profile_id"]
            if inputs.get("text") and isinstance(inputs["text"], str):
                caption = inputs["text"]
            if inputs.get("requirements_json") and isinstance(inputs["requirements_json"], str):
                requirements_json = inputs["requirements_json"]
            if inputs.get("Target_Prompt") and isinstance(inputs["Target_Prompt"], str):
                caption = inputs["Target_Prompt"]
        blob = self.images.get(digest or "") or self.images.get((digest or "") + ".png")
        if blob is None:
            for key, stored in self.images.items():
                if digest and sha256(stored) == digest:
                    blob = stored
                    break
        if blob is None:
            raise QAError("Local QA image is missing; upload the candidate first")
        outputs: dict[str, Any] = {}
        if "90" in classes or "GVDMetricReport" in classes.values():
            if self.clip_score_fn is None:
                raise QAError("CLIP scorer unavailable; adapter_required")
            audit = _RUNNER.clip_token_audit(caption)
            if self.enforce_clip_token_limit and audit["overlong"]:
                raise QAError("CLIP caption exceeds token budget")
            clip = float(self.clip_score_fn(blob, caption))
            report = {
                "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
                "profile_id": profile, "clip_text": clip, "clip_text_unit": self.clip_unit,
                "dino": float(self.dino_fn(blob)) if self.dino_fn is not None else None,
                "clip_image": float(self.clip_image_fn(blob)) if self.clip_image_fn is not None else None,
            }
            outputs["90"] = {"gvd_metrics": [report]}
            if self.wd14_fn is not None:
                outputs["30"] = {"tags": [self.wd14_fn(blob)]}
        if "91" in classes or "GVDQwenChecklist" in classes.values():
            if self.checklist_fn is None:
                raise QAError("Qwen checklist unavailable; start Caption V4 or inject a judge")
            requirements = json.loads(requirements_json)
            checks = self.checklist_fn(blob, requirements)
            qwen_pass = all(c.get("verdict") == "pass" for c in checks)
            outputs["91"] = {"gvd_qa": [{
                "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
                "profile_id": profile,
                "requirements_sha256": sha256(requirements_json.encode()),
                "checks": checks, "qwen_pass": qwen_pass,
            }]}
        if "92" in classes or "GVDRewardReport" in classes.values():
            if self.reward_fn is None:
                raise QAError("ImageReward unavailable; adapter_required")
            value = float(self.reward_fn(blob, caption))
            outputs["92"] = {"gvd_reward": [{
                "schema_version": 1, "attempt_id": attempt, "image_sha256": digest,
                "profile_id": profile, "image_reward": value, "unit": "imagereward_raw",
            }]}
        if not outputs:
            raise QAError("LocalQaClient graph has no GVD report nodes")
        item = {"status": {"completed": True, "status_str": "success"}, "outputs": outputs}
        atomic_json(journal, {"state": "completed", "attempt_id": attempt, "history": item})
        return item


def cpu_local_client(
    *,
    audit_caption: str = "",
    checklist_fn: CheckFn | None = None,
    download_wd14: bool = False,
    reference: bytes | None = None,
) -> LocalQaClient:
    from .scorers import clip_text_score, dino_image_score, image_reward_score
    from .wd14_cpu import cpu_wd14_fn
    dino_fn = None
    if reference is not None:
        dino_fn = lambda blob, ref=reference: dino_image_score(blob, ref)
    return LocalQaClient(
        clip_score_fn=clip_text_score,
        reward_fn=image_reward_score,
        wd14_fn=cpu_wd14_fn(download=download_wd14),
        dino_fn=dino_fn,
        checklist_fn=checklist_fn,
        audit_caption=audit_caption,
    )


def checklist_from_mapping(verdicts: dict[str, str]) -> CheckFn:
    def _fn(image: bytes, requirements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        checks = []
        for req in requirements:
            rid = req["id"]
            verdict = verdicts.get(rid, "unknown")
            checks.append({"id": rid, "verdict": verdict, "evidence": "injected"})
        return checks
    return _fn
