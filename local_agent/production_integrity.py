"""Fail-closed evidence contracts shared by the prompt-pack worker and watchdog."""
from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
import json
import shutil
import time
import uuid
from pathlib import Path


@contextmanager
def process_lock(path: Path, timeout: float = 0):
    """OS-held lock; process exit releases it without deleting ownership evidence."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    if handle.tell() == 0:
        handle.write(b"0")
        handle.flush()
    deadline = time.monotonic() + timeout
    locked = False
    try:
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("another production operation owns the process lock")
                time.sleep(.1)
        yield
    finally:
        if locked:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def write_evidence(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    return path


def copy_evidence(src: Path, dest: Path, expected: str | None = None) -> Path:
    digest = expected or sha256(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as source, dest.open("xb") as target:
        shutil.copyfileobj(source, target)
    if sha256(dest) != digest or sha256(src) != digest:
        raise ValueError("media changed while copying; preserved copy is not approved")
    return dest


def read_attempt_receipt(receipt: Path, root: Path, job: dict,
                         attempt: str, started: float) -> Path:
    record = json.loads(receipt.read_text(encoding="utf-8"))
    if (record.get("status") != "complete" or record.get("attempt_id") != attempt
            or record.get("story") != job["story"] or record.get("prompt") != job["prompt"]
            or not record.get("prompt_id")):
        raise ValueError("missing or mismatched attempt receipt")
    prefix = f"stories/{job['story']}/renders/{attempt}"
    save_nodes = [n for n in record.get("graph", {}).values()
                  if n.get("class_type") == "SaveImage"]
    if len(save_nodes) != 1 or save_nodes[0]["inputs"]["filename_prefix"] != prefix:
        raise ValueError("receipt graph is not from this attempt")
    outputs = record.get("verified_outputs") or []
    if len(outputs) != 1:
        raise ValueError("receipt must name exactly one verified still")
    output = outputs[0]
    path = Path(output["path"]).resolve()
    base = (root / "outputs/stories/_comfy_output").resolve()
    relative = path.relative_to(base).as_posix()
    if (not relative.startswith(prefix + "_") or path.suffix.lower() != ".png"
            or not path.is_file() or path.stat().st_mtime < started
            or output.get("sha256") != sha256(path)):
        raise ValueError("historical, changed, or foreign PNG rejected")
    return path


def qa_passed(record: dict, job: dict) -> bool:
    gate = record.get("accuracy_gate") or {}
    path = Path(record.get("png") or "")
    semantic = gate.get("semantic_evidence") or {}
    # Human review is authoritative and append-only.  Automated QA can miss
    # small anatomy faults (C001_last's malformed raised hand did exactly
    # that), so a sibling operator_review.json rejection must reopen the shot
    # without rewriting or deleting the original qa.json evidence.
    operator_review = path.parent / "operator_review.json"
    if operator_review.is_file():
        try:
            review = json.loads(operator_review.read_text(encoding="utf-8-sig"))
        except Exception:
            return False
        if review.get("decision") == "reject":
            return False
    # A caption alone is not a verdict; bind the exact VLM verdict to this image
    # and prompt. There is deliberately no implicit semantic success path.
    if gate.get("status") != "pass" or gate.get("semantic_check") != "pass":
        return False
    authored_hash = hashlib.sha256(str(job["prompt"]).encode()).hexdigest()
    import capabilities as caps
    bound = (
        path.is_file() and record.get("sha256") == sha256(path)
        and gate.get("image_sha256") == record["sha256"]
        and isinstance(gate.get("qa_prompt_sha256"), str)
        and isinstance(gate.get("generation_prompt_sha256"), str)
        and semantic.get("image_sha256") == record["sha256"]
        and semantic.get("qa_prompt_sha256") == gate["qa_prompt_sha256"]
        and semantic.get("generation_prompt_sha256") == gate["generation_prompt_sha256"]
        and semantic.get("model_sha256") == caps.QWEN25_VL_WEIGHTS_SHA256
        and semantic.get("projector_sha256") == caps.QWEN25_VL_MMPROJ_SHA256
        and semantic.get("runtime") == "llama.cpp"
        and semantic.get("verdict") == "pass"
    )
    if not bound:
        return False
    authored_bound = (
        gate.get("prompt_sha256") == authored_hash
        and gate.get("canonical_prompt_sha256") == authored_hash
        and semantic.get("prompt_sha256") == authored_hash
    )
    # Delivery-rubric recoveries review a shot-specific QA prompt while keeping
    # the authored generation prompt hash. Accept that binding so a restart
    # cannot re-render an already passed floor-POV still.
    delivery_bound = (
        gate.get("generation_prompt_sha256") == authored_hash
        and gate.get("prompt_sha256") == gate.get("qa_prompt_sha256")
        and gate.get("canonical_prompt_sha256") == gate.get("qa_prompt_sha256")
        and semantic.get("prompt_sha256") == gate.get("qa_prompt_sha256")
        and semantic.get("generation_prompt_sha256") == authored_hash
    )
    # A scene-only recovery may intentionally replace an impossible authored
    # prompt (for example: show the camera holder *and* use that person's
    # physical camcorder POV).  It is not a free-form prompt bypass: the
    # attempt must carry a hash-pinned local policy declaring the delivery
    # rubric, the exact VLM must validate that rubric, and the original
    # authored prompt hash remains on the top-level receipt.
    control = record.get("identity_control")
    if not isinstance(control, dict):
        control_path = path.parent / "identity_control.json"
        try:
            control = json.loads(control_path.read_text(encoding="utf-8"))
        except Exception:
            control = {}
    transformed_delivery_bound = (
        record.get("canonical_prompt_sha256") == authored_hash
        and gate.get("prompt_sha256") == gate.get("qa_prompt_sha256")
        and gate.get("canonical_prompt_sha256") == gate.get("qa_prompt_sha256")
        and semantic.get("prompt_sha256") == gate.get("qa_prompt_sha256")
        and semantic.get("generation_prompt_sha256") == gate.get("generation_prompt_sha256")
        and control.get("render_mode") == "scene_i2i_reframe"
        and control.get("semantic_assertions_prompt") == "delivery_qa_prompt"
        and isinstance(control.get("version"), str)
        and control["version"].startswith("c026-")
    )
    return bool(authored_bound or delivery_bound or transformed_delivery_bound)


def approved_still(key: str, stills: dict, jobs: dict, review: dict, revision: str) -> dict:
    record = stills.get(key) or {}
    if not qa_passed(record, jobs[key]):
        raise ValueError(f"{key}: semantic QA missing, failed, or stale")
    if (review.get("status") != "approved" or review.get("source_sha256") != revision
            or review.get("approval_kind") != "explicit_operator"
            or not review.get("approved_by") or not review.get("approved_at")
            or review.get("auto_approved_reason")):
        raise ValueError("explicit operator approval for this revision is required")
    item = (review.get("stills") or {}).get(key) or {}
    path = str(Path(record["png"]).resolve())
    if item.get("path") != path or item.get("sha256") != record["sha256"]:
        raise ValueError(f"{key}: approval does not match physical still")
    return {"story": key, "path": path, "sha256": record["sha256"]}


def bind_video_jobs(video_jobs: list[dict], still_jobs: list[dict], stills: dict,
                    review: dict, revision: str) -> list[dict]:
    jobs = {j["story"]: j for j in still_jobs}
    # All 204 candidates require QA and explicit approval before any video.
    approved = {key: approved_still(key, stills, jobs, review, revision) for key in jobs}
    result, previous_last = [], None
    for job in video_jobs:
        first_key = previous_last or job["story_start"]
        result.append({**job, "source_sha256": revision,
                       "references": {"first": approved[first_key],
                                      "last": approved[job["story_last"]]}})
        previous_last = job["story_last"]
    return result


def diagnose_stale(root: Path, ledger: Path, log: Path, stale_seconds: float,
                   now: float | None = None) -> dict | None:
    now = time.time() if now is None else now
    data = json.loads(ledger.read_text(encoding="utf-8"))
    if data.get("status") != "running":
        return None
    progress_time = float(data.get("progress_at") or data.get("started_at") or 0)
    timestamps = [progress_time, log.stat().st_mtime if log.exists() else 0]
    active_log = data.get("active_log")
    if active_log and Path(active_log).is_file():
        timestamps.append(Path(active_log).stat().st_mtime)
    owner_path = root / "work/runtime/image_render_owner.json"
    owner = owner_path.read_text(encoding="utf-8") if owner_path.exists() else None
    backend_logs = []
    try:
        owner_data = json.loads(owner or "{}")
        if data.get("supervisor_pid") and data.get("supervisor_pid") in (
                owner_data.get("pid"), owner_data.get("parent_pid")):
            backend_logs = [Path(p) for p in owner_data.get("backend_logs") or []]
    except ValueError:
        pass
    timestamps.extend(p.stat().st_mtime for p in backend_logs if p.exists())
    if now - max(timestamps) <= stale_seconds:
        return None
    logs = {}
    for path in [log, *([Path(active_log)] if active_log else []), *backend_logs]:
        logs[str(path)] = path.read_text(encoding="utf-8", errors="replace").splitlines()[-100:] if path.exists() else []
    health_dir = root / "work/runtime/image_render_runtime/logs"
    health = sorted(health_dir.glob("*.health*.json"), key=lambda p: p.stat().st_mtime)[-5:]
    diagnostics = {str(p): p.read_text(encoding="utf-8", errors="replace") for p in health}
    return {"observed_at": now, "reason": "stale_progress_and_logs",
            "stale_seconds": now - max(timestamps), "ledger": data,
            "owner_state": owner, "last_100_log_lines": logs, "startup_diagnostics": diagnostics,
            "retry_policy": "refuse while supervisor/backend ownership is live or uncertain"}


def snapshot_stale(root: Path, ledger: Path, log: Path, stale_seconds: float) -> Path | None:
    report = diagnose_stale(root, ledger, log, stale_seconds)
    if report is None:
        return None
    path = ledger.parent / "watchdog" / f"failure_{uuid.uuid4().hex}.json"
    write_evidence(path, report)
    return path


def physical_counts(prod: dict, review: dict) -> dict:
    stills, videos = prod.get("stills") or {}, prod.get("videos") or {}
    jobs = {j["story"]: j for j in prod.get("still_jobs") or []}
    counts = dict.fromkeys(("stills_generated", "stills_qa_passed", "stills_approved",
                           "stills_used_in_video", "videos_generated", "videos_qa_passed",
                           "videos_approved"), 0)
    approved = {}
    for key, record in stills.items():
        path = Path(record.get("png") or "")
        if not path.is_file() or record.get("sha256") != sha256(path):
            continue
        counts["stills_generated"] += 1
        if key not in jobs:
            continue
        if qa_passed(record, jobs[key]):
            counts["stills_qa_passed"] += 1
        try:
            approved[key] = approved_still(key, stills, jobs, review, prod.get("source_sha256"))
            counts["stills_approved"] += 1
        except ValueError:
            pass
    used = set()
    for record in videos.values():
        path = Path(record.get("mp4") or "")
        if not path.is_file() or record.get("sha256") != sha256(path):
            continue
        counts["videos_generated"] += 1
        counts["videos_qa_passed"] += record.get("qa_status") == "pass"
        counts["videos_approved"] += record.get("qa_status") == "pass" and record.get("approval_status") == "approved"
        for ref in (record.get("references") or {}).values():
            if approved.get(ref.get("story")) == ref:
                used.add(ref["story"])
    counts["stills_used_in_video"] = len(used)
    return counts
