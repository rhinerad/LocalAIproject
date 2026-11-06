"""Operator-controlled permission gate for local-agent GPU workloads.

This is intentionally a small, stdlib-only policy layer.  It controls model
loads initiated by this application; it reports (but does not indiscriminately
kill) unrelated Windows processes.  Defaulting to ``ask`` means an idle GPU is
never treated as blanket permission to load a model.

Concurrency model
-----------------
Several processes read and mutate the same state file (the GUI server, the
LXMF bridge, batch helpers).  Every mutation therefore holds both the
in-process ``threading.Lock`` and a cross-process lock on a sidecar file next
to ``STATE_FILE`` (``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere)
around its load+save, so one one-shot approval can never be consumed twice.
``snapshot()`` is strictly read-only: it never writes, and a transient read
failure returns the last good state instead of wiping pending approvals.

Approved keys are ``{"key": ..., "approved_at": epoch}`` records and expire
after ``APPROVAL_TTL_SECONDS``; legacy bare-string entries are still read.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
import uuid
from pathlib import Path

from atomic_io import atomic_write_json

if os.name == "nt":  # pragma: no cover - exercised on Windows only
    import msvcrt
else:
    import fcntl

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "runtime" / "gpu_gate.json"
_LOCK = threading.Lock()
_VALID_MODES = {"ask", "allow", "block"}
APPROVAL_TTL_SECONDS = 600
LOCK_TIMEOUT_SECONDS = 30.0
_LAST_GOOD: dict | None = None


def _blank() -> dict:
    return {"mode": "ask", "pending": [], "approved_keys": [], "history": [], "updated_at": time.time()}


# ── cross-process lock ────────────────────────────────────────────────────────

def _lock_path() -> Path:
    """Sidecar lock file next to the (monkeypatchable) STATE_FILE."""
    return STATE_FILE.with_name(STATE_FILE.name + ".lock")


def _acquire(fd: int) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"gpu_gate lock {_lock_path()} was held by another process for "
                    f"more than {LOCK_TIMEOUT_SECONDS:.0f}s")
            time.sleep(0.05)


def _release(fd: int) -> None:
    try:
        if os.name == "nt":
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


@contextlib.contextmanager
def _file_lock():
    """Hold the exclusive cross-process lock for the duration of a load+save."""
    path = _lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        _acquire(fd)
        try:
            yield
        finally:
            _release(fd)
    finally:
        os.close(fd)


# ── state file ────────────────────────────────────────────────────────────────

def _normalise_approved(entries, *, fallback_ts: float, now: float) -> list[dict]:
    """Coerce approved entries to records and drop those past the TTL."""
    out: list[dict] = []
    for entry in entries or []:
        if isinstance(entry, str):  # legacy bare-string entry
            entry = {"key": entry, "approved_at": fallback_ts}
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        try:
            approved_at = float(entry.get("approved_at") or fallback_ts)
        except (TypeError, ValueError):
            approved_at = fallback_ts
        if now - approved_at > APPROVAL_TTL_SECONDS:
            continue
        out.append({"key": str(entry["key"]), "approved_at": approved_at})
    return out


def _load() -> dict:
    """Read the state file.

    Returns a blank state only when the file is missing or is not valid JSON.
    Any other ``OSError`` (permission denied, AV/indexer lock, directory in
    the way) propagates: a transient read failure must never be mistaken for
    "no pending approvals".
    """
    global _LAST_GOOD
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _blank()
    except ValueError:  # json.JSONDecodeError and UnicodeDecodeError are ValueErrors
        return _blank()
    if not isinstance(raw, dict):
        return _blank()
    if raw.get("mode") not in _VALID_MODES:
        raw["mode"] = "ask"
    raw.setdefault("pending", [])
    raw.setdefault("history", [])
    now = time.time()
    try:
        fallback_ts = float(raw.get("updated_at") or now)
    except (TypeError, ValueError):
        fallback_ts = now
    raw["approved_keys"] = _normalise_approved(
        raw.get("approved_keys"), fallback_ts=fallback_ts, now=now)
    _LAST_GOOD = json.loads(json.dumps(raw))
    return raw


def _save(state: dict) -> None:
    global _LAST_GOOD
    state["updated_at"] = time.time()
    atomic_write_json(STATE_FILE, state)
    _LAST_GOOD = json.loads(json.dumps(state))


def snapshot() -> dict:
    """Read-only view of the gate. Never writes; never wipes state on a read error."""
    with _LOCK:
        try:
            # Pending permissions intentionally persist until the operator makes
            # a decision. A request is tied to its specific workload key, and an
            # approval remains one-shot, so retaining the card is not blanket GPU
            # consent for a later unrelated load.
            return _load()
        except OSError:
            state = json.loads(json.dumps(_LAST_GOOD)) if _LAST_GOOD else _blank()
            state["stale"] = True
            return state


def set_mode(mode: object) -> dict:
    mode = str(mode or "").lower()
    if mode not in _VALID_MODES:
        raise ValueError("mode must be ask, allow, or block")
    with _LOCK, _file_lock():
        state = _load()
        state["mode"] = mode
        _save(state)
        return state


def _approved_index(state: dict, key: str) -> int | None:
    for index, entry in enumerate(state.get("approved_keys") or []):
        if isinstance(entry, dict) and entry.get("key") == key:
            return index
    return None


def request(workload: str, *, source: str, detail: str = "", key: str = "") -> dict:
    """Return ``granted`` or create/reuse a visible pending permission card."""
    workload, source, detail, key = map(str, (workload, source, detail, key))
    with _LOCK, _file_lock():
        state = _load()
        mode = state["mode"]
        if mode == "allow":
            return {"granted": True, "mode": mode, "request": None}
        if mode == "block":
            return {"granted": False, "mode": mode, "blocked": True, "request": None}
        if key:
            index = _approved_index(state, key)
            if index is not None:
                state["approved_keys"].pop(index)  # one model-load attempt only
                _save(state)
                return {"granted": True, "mode": mode, "request": None}
        for item in state["pending"]:
            if item.get("key") == key and key:
                return {"granted": False, "mode": mode, "request": item}
        item = {"id": "gpu_" + uuid.uuid4().hex[:12], "workload": workload,
                "source": source, "detail": detail[:500], "key": key,
                "created_at": time.time()}
        state["pending"].append(item)
        _save(state)
        return {"granted": False, "mode": mode, "request": item}


def decide(request_id: object, action: object) -> dict:
    action = str(action or "").lower()
    if action not in {"approve", "deny"}:
        raise ValueError("action must be approve or deny")
    with _LOCK, _file_lock():
        state = _load()
        chosen = next((x for x in state["pending"] if x.get("id") == str(request_id)), None)
        if not chosen:
            previous = next((x for x in state.get("history", [])
                             if x.get("id") == str(request_id)), None)
            if previous:
                # Browsers can retry a click after a slow refresh. Treat the
                # same request decision as idempotent instead of reporting an
                # expiry/error that makes the operator think consent vanished.
                return previous
            raise ValueError("GPU permission request was not found")
        state["pending"] = [x for x in state["pending"] if x is not chosen]
        chosen.update({"decision": action, "decided_at": time.time()})
        if action == "approve" and chosen.get("key"):
            state["approved_keys"].append(
                {"key": str(chosen["key"]), "approved_at": time.time()})
        state["history"] = ([chosen] + state["history"])[:30]
        # Approval is deliberately one-shot. The workload retries, creates a
        # fresh intent next time, and must ask again under the default policy.
        _save(state)
        return chosen
