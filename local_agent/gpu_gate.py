"""Operator-controlled permission gate for local-agent GPU workloads.

This is intentionally a small, stdlib-only policy layer.  It controls model
loads initiated by this application; it reports (but does not indiscriminately
kill) unrelated Windows processes.  Defaulting to ``ask`` means an idle GPU is
never treated as blanket permission to load a model.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "runtime" / "gpu_gate.json"
_LOCK = threading.Lock()
_VALID_MODES = {"ask", "allow", "block"}


def _blank() -> dict:
    return {"mode": "ask", "pending": [], "approved_keys": [], "history": [], "updated_at": time.time()}


def _load() -> dict:
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if raw.get("mode") not in _VALID_MODES:
            raw["mode"] = "ask"
        raw.setdefault("pending", [])
        raw.setdefault("approved_keys", [])
        raw.setdefault("history", [])
        return raw
    except Exception:
        return _blank()


def _save(state: dict) -> None:
    state["updated_at"] = time.time()
    atomic_write_text(STATE_FILE, json.dumps(state, indent=2))


def snapshot() -> dict:
    with _LOCK:
        state = _load()
        # Pending permissions intentionally persist until the operator makes a
        # decision. A request is tied to its specific workload key, and an
        # approval remains one-shot, so retaining the card is not blanket GPU
        # consent for a later unrelated load.
        _save(state)
        return state


def set_mode(mode: object) -> dict:
    mode = str(mode or "").lower()
    if mode not in _VALID_MODES:
        raise ValueError("mode must be ask, allow, or block")
    with _LOCK:
        state = _load()
        state["mode"] = mode
        _save(state)
        return state


def request(workload: str, *, source: str, detail: str = "", key: str = "") -> dict:
    """Return ``granted`` or create/reuse a visible pending permission card."""
    workload, source, detail, key = map(str, (workload, source, detail, key))
    with _LOCK:
        state = _load()
        mode = state["mode"]
        if mode == "allow":
            return {"granted": True, "mode": mode, "request": None}
        if mode == "block":
            return {"granted": False, "mode": mode, "blocked": True, "request": None}
        if key and key in state["approved_keys"]:
            state["approved_keys"].remove(key)  # one model-load attempt only
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
    with _LOCK:
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
            state["approved_keys"].append(chosen["key"])
        state["history"] = ([chosen] + state["history"])[:30]
        # Approval is deliberately one-shot. The workload retries, creates a
        # fresh intent next time, and must ask again under the default policy.
        _save(state)
        return chosen
