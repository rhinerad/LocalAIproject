#!/usr/bin/env python3
"""Durable, source-bound outbound LXMF message schedules.

The scheduler is deliberately transport-agnostic.  It stores only a paired
LXMF identity, a bounded message template and timing metadata; the running
bridge supplies the actual delivery callback.  A queued LXMF message is not
claimed to be delivered, because radio/store-and-forward delivery can occur
after the workstation queues it.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Callable

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "lxmf"
STATE = RUNTIME / "phone_schedules.json"
AUDIT = RUNTIME / "phone_schedule_audit.jsonl"
_LOCK = threading.Lock()
MIN_INTERVAL_SECONDS = 10
MAX_INTERVAL_SECONDS = 3600
MAX_COUNT = 120
MAX_DURATION_SECONDS = 24 * 60 * 60
# A lease is written *before* an LXMF send.  It prevents two bridge loops from
# independently queueing the same counter.  Expired leases are deliberately
# marked uncertain instead of being retried: after a process crash we cannot
# know whether Reticulum accepted the outbound message, and duplicate remote
# messages are worse than asking the operator to reschedule the remainder.
DISPATCH_LEASE_SECONDS = 120


class ScheduleError(ValueError):
    pass


class ScheduleBlocked(RuntimeError):
    """The receiving identity is no longer eligible for an outbound schedule."""


def _state_path(path: Path | None) -> Path:
    """Resolve paths at call time so tests cannot capture the live queue."""
    return STATE if path is None else Path(path)


def _audit_path(path: Path | None) -> Path:
    return AUDIT if path is None else Path(path)


def _load(path: Path | None = None) -> dict:
    path = _state_path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {"version": 1, "jobs": {}}
    if not isinstance(data, dict) or not isinstance(data.get("jobs"), dict):
        data = {"version": 1, "jobs": {}}
    return data


def _save(data: dict, path: Path | None = None) -> None:
    path = _state_path(path)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _audit(event: str, job: dict, *, detail: str = "", path: Path | None = None,
           counter: int | None = None) -> None:
    path = _audit_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    template = str(job.get("template", ""))
    record = {
        "at": time.time(), "event": event, "job_id": str(job.get("id", "")),
        "identity": str(job.get("identity", "")),
        "counter": (int(counter) if counter is not None else
                    int(job.get("start", 0)) + int(job.get("queued_count", 0))),
        "message_sha256": hashlib.sha256(template.encode("utf-8")).hexdigest(),
        "message_chars": len(template), "detail": str(detail)[:300],
    }
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _identity(value: object) -> str:
    identity = str(value or "").strip().lower()
    if len(identity) != 32 or any(char not in "0123456789abcdef" for char in identity):
        raise ScheduleError("a paired phone identity is required")
    return identity


def create(identity: object, message: object, interval_seconds: object, count: object,
           *, start: object = 0, now: float | None = None, path: Path | None = None) -> dict:
    identity = _identity(identity)
    template = str(message or "").strip()
    if not template or len(template) > 500:
        raise ScheduleError("message must contain 1 to 500 characters")
    try:
        interval, total, first = int(interval_seconds), int(count), int(start)
    except (TypeError, ValueError) as exc:
        raise ScheduleError("interval_seconds, count and start must be integers") from exc
    if not MIN_INTERVAL_SECONDS <= interval <= MAX_INTERVAL_SECONDS:
        raise ScheduleError(f"interval_seconds must be {MIN_INTERVAL_SECONDS} to {MAX_INTERVAL_SECONDS}")
    if not 1 <= total <= MAX_COUNT or interval * max(total - 1, 1) > MAX_DURATION_SECONDS:
        raise ScheduleError(f"count must be 1 to {MAX_COUNT} within one day")
    if not -1_000_000 <= first <= 1_000_000:
        raise ScheduleError("start counter is outside the permitted range")
    moment = time.time() if now is None else float(now)
    job = {
        "id": f"phone_schedule_{uuid.uuid4().hex[:16]}", "identity": identity,
        "template": template, "interval_seconds": interval, "count": total, "start": first,
        "queued_count": 0, "attempt_count": 0, "created_at": moment, "next_at": moment,
        "status": "active", "last_error": "",
    }
    with _LOCK:
        data = _load(path)
        data["jobs"][job["id"]] = job
        _save(data, path)
    _audit("created", job)
    return public(job)


def public(job: dict) -> dict:
    return {
        "id": job["id"], "status": job["status"], "interval_seconds": job["interval_seconds"],
        "count": job["count"], "start": job["start"], "queued_count": job.get("queued_count", 0),
        "next_at": job.get("next_at"), "message_chars": len(str(job.get("template", ""))),
        "dispatching": bool(job.get("dispatch_lease")),
        "delivery_note": "Each item is queued to LXMF; radio delivery is not guaranteed by this workstation.",
    }


def list_for_identity(identity: object, *, path: Path | None = None) -> list[dict]:
    key = _identity(identity)
    with _LOCK:
        return [public(job) for job in _load(path)["jobs"].values() if job.get("identity") == key]


def cancel(identity: object, job_id: object, *, path: Path | None = None) -> dict:
    key, requested = _identity(identity), str(job_id or "").strip()
    with _LOCK:
        data = _load(path)
        job = data["jobs"].get(requested)
        if not job or job.get("identity") != key:
            raise ScheduleError("scheduled message job was not found for this phone")
        if job.get("status") in {"active", "uncertain"}:
            job["status"] = "cancelled"
            job["cancelled_at"] = time.time()
            _save(data, path)
    _audit("cancelled", job)
    return public(job)


def dispatch_due(send: Callable[[str, str, dict], None], *, now: float | None = None,
                 path: Path | None = None) -> list[dict]:
    """Queue every due message once.  Successful queueing advances the counter.

    ``send`` must raise ``ScheduleBlocked`` for an inactive/revoked recipient.
    Other errors are retried no sooner than 30 seconds or the configured
    interval, whichever is smaller.  In no case is a failed queue attempt
    counted as a sent message.
    """
    moment = time.time() if now is None else float(now)
    # Claim and durably save every due job before touching the transport.  The
    # previous copy-then-send sequence allowed two scheduler loops to send the
    # same counter before either one advanced queued_count.
    with _LOCK:
        data = _load(path)
        jobs: list[dict] = []
        changed = False
        for job in data["jobs"].values():
            lease = job.get("dispatch_lease")
            if lease and float(lease.get("expires_at", 0)) <= moment:
                # The old process may have handed this message to Reticulum
                # immediately before it died.  Retrying would manufacture a
                # phantom duplicate, so preserve an explicit human-review
                # state instead.
                job.pop("dispatch_lease", None)
                job["status"] = "uncertain"
                job["last_error"] = "dispatch lease expired; queue result is unknown"
                _audit("lease_expired_unknown", job, detail="automatic retry refused")
                changed = True
                continue
            if (job.get("status") != "active" or lease or
                    float(job.get("next_at", 0)) > moment):
                continue
            counter = int(job["start"]) + int(job.get("queued_count", 0))
            lease_id = uuid.uuid4().hex
            job["dispatch_lease"] = {
                "id": lease_id, "counter": counter, "claimed_at": moment,
                "expires_at": moment + DISPATCH_LEASE_SECONDS,
            }
            jobs.append(dict(job))
            changed = True
        if changed:
            _save(data, path)
    results: list[dict] = []
    for due in jobs:
        lease = due["dispatch_lease"]
        lease_id, counter = str(lease["id"]), int(lease["counter"])
        message = str(due["template"]).replace("{n}", str(counter))
        try:
            send(due["identity"], message, {"job_id": due["id"], "counter": counter})
            outcome, detail = "queued", "queued to LXMF"
        except ScheduleBlocked as exc:
            outcome, detail = "blocked", str(exc)
        except Exception as exc:
            outcome, detail = "retry", f"{type(exc).__name__}: {exc}"
        with _LOCK:
            data = _load(path)
            job = data["jobs"].get(due["id"])
            current_lease = job.get("dispatch_lease") if job else None
            if (not job or job.get("status") != "active" or
                    not current_lease or current_lease.get("id") != lease_id):
                if job:
                    _audit("lease_lost", job, detail="delivery outcome ignored after lease changed")
                continue
            job.pop("dispatch_lease", None)
            job["attempt_count"] = int(job.get("attempt_count", 0)) + 1
            if outcome == "queued":
                job["queued_count"] = int(job.get("queued_count", 0)) + 1
                job["last_error"] = ""
                job["next_at"] = moment + int(job["interval_seconds"])
                if int(job["queued_count"]) >= int(job["count"]):
                    job["status"] = "complete"
                # queued_count has just been advanced, so preserve the actual
                # counter sent rather than recording the next counter value.
                _audit("queued", job, detail=detail, counter=counter)
            elif outcome == "blocked":
                job["status"] = "blocked"
                job["last_error"] = detail[:300]
                _audit("blocked", job, detail=detail)
            else:
                job["last_error"] = detail[:300]
                job["next_at"] = moment + min(int(job["interval_seconds"]), 30)
                _audit("queue_failed", job, detail=detail)
            data["jobs"][job["id"]] = job
            _save(data, path)
            results.append({"job_id": job["id"], "outcome": outcome, "counter": counter,
                            "status": job["status"]})
    return results
