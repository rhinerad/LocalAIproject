#!/usr/bin/env python3
"""Transport-agnostic media job queue. stdlib only, no downloads.

Directory layout under local_agent/media_queue/:
    pending/      accepted, not yet claimed
    processing/   claimed by the watcher
    done/         completed successfully
    failed/       terminal failure
    cancelled/    operator-cleared pending jobs, retained as evidence

State transitions use tmp-write + os.replace() so a crash never leaves a
half-written file. A crashed watcher leaves jobs in processing/; recover_stale()
moves them back to pending/ on the next watcher startup.
"""
from __future__ import annotations

import calendar
import json
import os
import time
import uuid
from pathlib import Path

from atomic_io import atomic_write_text
import router

HERE = Path(__file__).resolve().parent
QUEUE_ROOT = HERE / "media_queue"
_STATES = ("pending", "processing", "done", "failed", "cancelled")


def _ensure() -> None:
    for d in _STATES:
        (QUEUE_ROOT / d).mkdir(parents=True, exist_ok=True)


def _write_atomic(path: Path, data: dict) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def source_stat(path: object) -> dict | None:
    """Size + mtime of a job's source file, recorded at enqueue time.

    Lets a later identical request reuse a *completed* job's result only when
    the file it analysed is the same unchanged file (same size and mtime), never
    a newer file that happens to share the path.
    """
    raw = str(path or "").strip()
    if not raw:
        return None
    try:
        st = os.stat(raw)
    except OSError:
        return None
    return {"path": raw, "size": int(st.st_size), "mtime_ns": int(st.st_mtime_ns)}


def _public_job_args(args: dict | None) -> dict:
    return {k: v for k, v in (args or {}).items() if not str(k).startswith("__")}


def _epoch(value: str | None) -> int | None:
    try:
        return calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def _norm_source(value: object) -> str:
    raw = str(value or "").strip()
    return os.path.normcase(os.path.normpath(raw)) if raw else ""


def find_completed(kind: str, args: dict, *, source: str | None = None) -> dict | None:
    """Newest done/ job with the same kind and public args over an unchanged file.

    A job that recorded ``source_stat`` must match the file's current size and
    mtime exactly. An older job without it (queued before that field existed)
    is reused only if the file was last modified no later than the second the
    job was queued. Failed and cancelled jobs are never reused. Returns the
    job dict with ``status`` = "done", or None.
    """
    _ensure()
    want = _public_job_args(args)
    stat = source_stat(source) if source else None
    candidates: list[dict] = []
    for fp in (QUEUE_ROOT / "done").glob("*.json"):
        try:
            job = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(job, dict) or job.get("kind") != kind:
            continue
        if _public_job_args(job.get("args")) != want:
            continue
        if not str(job.get("result") or "").strip():
            continue
        if source:
            if stat is None:
                continue
            recorded = job.get("source_stat")
            if isinstance(recorded, dict):
                try:
                    same = (int(recorded.get("size")) == stat["size"]
                            and int(recorded.get("mtime_ns")) == stat["mtime_ns"])
                except (TypeError, ValueError):
                    same = False
                if not same:
                    continue
            else:
                queued_epoch = _epoch(job.get("queued_at"))
                if queued_epoch is None or stat["mtime_ns"] // 1_000_000_000 > queued_epoch:
                    continue
        job["status"] = "done"
        candidates.append(job)
    if not candidates:
        return None
    candidates.sort(key=lambda j: str(j.get("done_at") or j.get("queued_at") or ""),
                    reverse=True)
    return candidates[0]


def find_for_path(path: object) -> list[dict]:
    """Every job in any state whose args name this source file, newest first."""
    _ensure()
    want = _norm_source(path)
    if not want:
        return []
    rows: list[dict] = []
    for state in _STATES:
        for fp in (QUEUE_ROOT / state).glob("*.json"):
            try:
                job = json.loads(fp.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(job, dict):
                continue
            args = job.get("args") or {}
            sources = [args.get("path"), args.get("video_path")]
            images = args.get("images")
            if isinstance(images, list):
                sources.extend(images)
            if any(_norm_source(s) == want for s in sources if s):
                job["status"] = state
                rows.append(job)
    rows.sort(key=lambda j: str(j.get("queued_at") or ""), reverse=True)
    return rows


def enqueue(kind: str, args: dict, *, priority: str = "batch",
            source: str | None = None) -> dict:
    """Create a new pending job, coalescing an identical queued request.

    A duplicate media attachment should not turn into duplicate inference work.
    Completed, failed, and cancelled jobs remain independent evidence records.
    ``source`` (the analysed file) records ``source_stat`` on the job so
    find_completed() can later hand an identical request the finished result.
    """
    if priority not in {"interactive", "batch"}:
        raise ValueError("priority must be 'interactive' or 'batch'")
    _ensure()
    for state in ("pending", "processing"):
        for fp in (QUEUE_ROOT / state).glob("*.json"):
            try:
                prior = json.loads(fp.read_text(encoding="utf-8"))
                if prior.get("kind") == kind and prior.get("args") == args:
                    # A live operator request can duplicate earlier batch work.
                    # Keep one evidence record, but let the live request win.
                    if (priority == "interactive" and prior.get("priority", "batch") != "interactive"
                            and state == "pending"):
                        prior["priority"] = "interactive"
                        _write_atomic(fp, prior)
                    prior["deduplicated"] = True
                    return prior
            except Exception:
                continue
    job: dict = {
        "id": uuid.uuid4().hex[:16],
        "kind": kind,
        "args": args,
        "priority": priority,
        "queued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    stat = source_stat(source) if source else None
    if stat:
        job["source_stat"] = stat
    _write_atomic(QUEUE_ROOT / "pending" / f"{job['id']}.json", job)
    return job


def clear_pending(reason: str = "operator cleared media queue") -> int:
    """Preserve and clear every *pending* job from the active queue.

    Processing work is deliberately not interrupted: it may already be using a
    model or writing a result. Each cleared record is retained in cancelled/
    with its original arguments and timestamps, never deleted.
    """
    _ensure()
    n = 0
    for fp in sorted((QUEUE_ROOT / "pending").glob("*.json"),
                     key=lambda p: p.stat().st_mtime):
        try:
            job = json.loads(fp.read_text(encoding="utf-8"))
            job["cancelled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job["cancel_reason"] = reason
            target = QUEUE_ROOT / "cancelled" / fp.name
            _write_atomic(target, job)
            try:
                os.remove(fp)
            except FileNotFoundError:
                continue
            n += 1
        except Exception:
            continue
    return n


def _move_cancelled(src: Path, job: dict, reason: str) -> None:
    job["cancelled_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["cancel_reason"] = str(reason)
    job["progress"] = {"stage": "cancelled"}
    _write_atomic(QUEUE_ROOT / "cancelled" / src.name, job)
    try:
        os.remove(src)
    except FileNotFoundError:
        pass


def cancel(job_id: str) -> dict:
    """Cancel one queued job without deleting its evidence record.

    A pending job moves immediately. A processing job receives a cooperative
    flag that the watcher observes at the next safe media boundary.
    """
    _ensure()
    for state in ("pending", "processing", "done", "failed", "cancelled"):
        path = QUEUE_ROOT / state / f"{job_id}.json"
        if not path.is_file():
            continue
        if state == "pending":
            job = json.loads(path.read_text(encoding="utf-8"))
            _move_cancelled(path, job, "operator cancelled")
            return {"ok": True, "state": "cancelled", "message": "Cancelled pending media job."}
        if state == "processing":
            job = json.loads(path.read_text(encoding="utf-8"))
            job["cancel_requested_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job["progress"] = {"stage": "cancelling"}
            _write_atomic(path, job)
            return {"ok": True, "state": "cancelling", "message": "Cancellation requested; the current safe step will finish first."}
        return {"ok": False, "state": state, "message": f"Job is already {state}; nothing was cancelled."}
    return {"ok": False, "state": "unknown", "message": "Unknown media job id."}


def cancel_requested(job_id: str) -> bool:
    path = QUEUE_ROOT / "processing" / f"{job_id}.json"
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("cancel_requested_at"))
    except Exception:
        return False


def finish_cancel(job_id: str, reason: str = "operator cancelled") -> bool:
    """Move a cooperatively stopped processing job into cancelled/."""
    _ensure()
    path = QUEUE_ROOT / "processing" / f"{job_id}.json"
    if not path.is_file():
        return False
    try:
        _move_cancelled(path, json.loads(path.read_text(encoding="utf-8")), reason)
        return True
    except FileNotFoundError:
        return False


def set_progress(job_id: str, stage: str, done: int | None = None,
                 total: int | None = None) -> None:
    path = QUEUE_ROOT / "processing" / f"{job_id}.json"
    if not path.is_file():
        return
    try:
        job = json.loads(path.read_text(encoding="utf-8"))
        progress = {"stage": str(stage)}
        if done is not None:
            progress["done"] = int(done)
        if total is not None:
            progress["total"] = int(total)
        job["progress"] = progress
        _write_atomic(path, job)
    except Exception:
        pass


def claim_next(kind: str | None = None) -> dict | None:
    """Atomically claim the oldest pending job, optionally filtered by kind.

    Returns None if no matching job is pending.
    """
    _ensure()
    # Direct operator work is first, FIFO within each tier. Batch work must not
    # leave a live phone/photo request waiting behind old bulk extraction.
    candidates = []
    for fp in (QUEUE_ROOT / "pending").glob("*.json"):
        try:
            job = json.loads(fp.read_text(encoding="utf-8"))
            candidates.append((0 if job.get("priority", "batch") == "interactive" else 1,
                               fp.stat().st_mtime, fp, job))
        except Exception:
            continue
    candidates.sort(key=lambda value: (value[0], value[1]))
    for _priority, _mtime, fp, job in candidates:
        try:
            if kind is not None and job.get("kind") != kind:
                continue
            job["claimed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            job["started_at"] = job["claimed_at"]
            job["progress"] = {"stage": "loading"}
            target = QUEUE_ROOT / "processing" / fp.name
            _write_atomic(target, job)
            try:
                os.remove(fp)
            except FileNotFoundError:
                pass
            return job
        except Exception:
            continue
    return None


def get(job_id: str) -> dict | None:
    """Load one job from any queue state. Adds ``status`` (pending/processing/done/failed/cancelled).

    Used to restamp chat activity cards. Does not invent a generated filename.
    """
    _ensure()
    identifier = str(job_id or "").strip()
    if not identifier:
        return None
    for state in _STATES:
        path = QUEUE_ROOT / state / f"{identifier}.json"
        if not path.is_file():
            continue
        try:
            job = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(job, dict):
            return None
        job["status"] = state
        return job
    return None


def complete(job_id: str, result: str) -> None:
    """Move a processing job to done/ with its result string."""
    _ensure()
    src = QUEUE_ROOT / "processing" / f"{job_id}.json"
    if not src.is_file():
        return
    job = json.loads(src.read_text(encoding="utf-8"))
    job["done_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["result"] = result
    _write_atomic(QUEUE_ROOT / "done" / src.name, job)
    try:
        os.remove(src)
    except FileNotFoundError:
        pass


def fail(job_id: str, error: str) -> None:
    """Move a processing job to failed/ with its error string."""
    _ensure()
    src = QUEUE_ROOT / "processing" / f"{job_id}.json"
    if not src.is_file():
        return
    job = json.loads(src.read_text(encoding="utf-8"))
    job["failed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    job["error"] = error
    _write_atomic(QUEUE_ROOT / "failed" / src.name, job)
    try:
        os.remove(src)
    except FileNotFoundError:
        pass


def requeue(job_id: str, reason: str) -> bool:
    """Return one processing job to pending after a cooperative interruption.

    This is not a failure: the original request and its identity remain intact,
    while the preserved reason makes the interruption auditable.
    """
    _ensure()
    src = QUEUE_ROOT / "processing" / f"{job_id}.json"
    if not src.is_file():
        return False
    try:
        job = json.loads(src.read_text(encoding="utf-8"))
        event = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                 "reason": str(reason)}
        job.setdefault("preemptions", []).append(event)
        job.pop("claimed_at", None)
        _write_atomic(QUEUE_ROOT / "pending" / src.name, job)
        os.remove(src)
        return True
    except FileNotFoundError:
        return False


def recover_stale() -> int:
    """Move any processing/ jobs back to pending/ (call on watcher startup)."""
    _ensure()
    n = 0
    for fp in (QUEUE_ROOT / "processing").glob("*.json"):
        try:
            os.replace(fp, QUEUE_ROOT / "pending" / fp.name)
            n += 1
        except Exception:
            pass
    return n


def _elapsed(value: str | None) -> int:
    try:
        # Queue timestamps are explicitly UTC (the trailing Z).  time.mktime()
        # interprets them as local time, which produces a timezone-sized timer
        # error on the desktop UI.
        then = calendar.timegm(time.strptime(str(value), "%Y-%m-%dT%H:%M:%SZ"))
        return max(0, int(time.time() - then))
    except Exception:
        return 0


def _name(job: dict) -> str:
    args = job.get("args") or {}
    source = args.get("path") or args.get("video_path") or ""
    if not source and args.get("images"):
        source = args["images"][0]
    return Path(str(source)).name or str(job.get("kind") or "media")


def list_queue() -> dict:
    """Cheap, UI-ready queue snapshot; never loads a media model."""
    _ensure()
    result: dict = {}
    pending_jobs: list[dict] = []
    for d in _STATES:
        jobs = []
        for fp in sorted((QUEUE_ROOT / d).glob("*.json"),
                         key=lambda p: p.stat().st_mtime):
            try:
                j = json.loads(fp.read_text(encoding="utf-8"))
                row = {"id": j.get("id"), "kind": j.get("kind"),
                       "priority": j.get("priority", "batch"), "status": d,
                       "name": _name(j), "queued_at": j.get("queued_at"),
                       "started_at": j.get("started_at"),
                       "elapsed_seconds": _elapsed(j.get("queued_at")),
                       "progress": j.get("progress") or {"stage": d}}
                jobs.append(row)
                if d == "pending":
                    pending_jobs.append(row)
            except Exception:
                pass
        result[d] = jobs
    owned, _why = router.queue_owner()
    render_busy = owned or router.comfy_listening()
    free_mb = router.gpu_free_mb()
    ordered = sorted(pending_jobs, key=lambda row: (0 if row["priority"] == "interactive" else 1,
                                                     row["queued_at"] or ""))
    for index, row in enumerate(ordered):
        if render_busy:
            row["waiting_reason"] = "waiting for the GPU — a render is using it"
        elif row["kind"] == "transcribe":
            row["waiting_reason"] = "queued for CPU transcription"
        elif free_mb is None or free_mb < 1024:
            row["waiting_reason"] = "waiting for VRAM to free up"
        else:
            row["waiting_reason"] = f"queued — {index} item(s) ahead"
    return result
