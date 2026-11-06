"""OS-held cooperative GPU lease. JSON owner state is evidence, not the lock."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Iterator
from contextlib import contextmanager

from .paths import GvdLayout

LEASE_TTL_S = 900.0


@dataclass
class GpuLease:
    generation: int
    owner_pid: int
    created: float
    job_id: str
    attempt_id: str
    heartbeat: float
    family_key: str


class LeaseContention(RuntimeError):
    pass


def _lock(layout: GvdLayout):
    from production_integrity import process_lock
    return process_lock(layout.lease_lock, timeout=0)


def _read(layout: GvdLayout) -> dict[str, Any] | None:
    if not layout.lease_json.exists():
        return None
    try:
        return json.loads(layout.lease_json.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write(layout: GvdLayout, payload: dict[str, Any]) -> None:
    layout.state_dir.mkdir(parents=True, exist_ok=True)
    tmp = layout.lease_json.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(layout.lease_json)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


@contextmanager
def acquire(
    layout: GvdLayout,
    *,
    job_id: str,
    attempt_id: str,
    family_key: str = "",
    allow_foreign: bool = False,
) -> Iterator[GpuLease]:
    """Acquire exclusive GPU lease. Does not cancel foreign Comfy jobs."""
    layout.ensure()
    with _lock(layout):
        current = _read(layout)
        now = time.time()
        # Fix 2026-09-23 (readiness-audit finding 1.3): a same-PID nested
        # acquire() previously reused the outer lease's `generation` number
        # unchanged, so the INNER context's release (in its own `finally`,
        # below) matched that same generation and cleared ownership
        # (owner_pid=0) while the OUTER context was still logically active
        # and believed it still held the lease. `holders` makes same-PID
        # reentrancy a true, LIFO-safe refcount: only the outermost
        # release actually clears ownership.
        reentrant = False
        if current:
            owner = int(current.get("owner_pid") or 0)
            alive = _pid_alive(owner)
            expired = now - float(current.get("heartbeat") or 0) > LEASE_TTL_S
            if alive and owner != os.getpid():
                if not allow_foreign:
                    raise LeaseContention(
                        f"GPU lease held by pid {owner} job={current.get('job_id')}"
                    )
            if alive and owner == os.getpid():
                generation = int(current.get("generation") or 0)
                reentrant = True
            elif not alive or expired:
                generation = int(current.get("generation") or 0) + 1
            else:
                raise LeaseContention("foreign GPU lease is live")
        else:
            generation = 1
        holders = (int(current.get("holders") or 1) + 1) if (reentrant and current) else 1
        lease = GpuLease(
            generation=generation,
            owner_pid=os.getpid(),
            created=now,
            job_id=job_id,
            attempt_id=attempt_id,
            heartbeat=now,
            family_key=family_key,
        )
        _write(layout, {
            "generation": lease.generation,
            "owner_pid": lease.owner_pid,
            "created": lease.created,
            "job_id": lease.job_id,
            "attempt_id": lease.attempt_id,
            "heartbeat": lease.heartbeat,
            "family_key": lease.family_key,
            "holders": holders,
        })
    try:
        yield lease
    finally:
        with _lock(layout):
            held = _read(layout) or {}
            if int(held.get("owner_pid") or 0) == os.getpid() and int(
                held.get("generation") or 0
            ) == lease.generation:
                remaining = int(held.get("holders") or 1) - 1
                held["heartbeat"] = time.time()
                if remaining <= 0:
                    held["released"] = True
                    held["owner_pid"] = 0
                    held["holders"] = 0
                else:
                    # An outer same-PID acquire() is still active; do not
                    # clear ownership out from under it.
                    held["holders"] = remaining
                _write(layout, held)


def heartbeat(layout: GvdLayout, lease: GpuLease) -> None:
    with _lock(layout):
        held = _read(layout) or {}
        if int(held.get("generation") or 0) != lease.generation:
            raise LeaseContention("lease generation changed")
        held["heartbeat"] = time.time()
        _write(layout, held)
