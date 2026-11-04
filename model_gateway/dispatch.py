"""Bookkeeping for the plan-only gateway: last call, last plan, last fallback.

The gateway never decides *whether* a turn asks for a plan here; that is
``router.decide()`` via ``policy.wants_cloud_plan``. This module records what
happened so ``router.status()`` and the logs can show it.
"""
from __future__ import annotations

import logging
import threading
import time

from .adapters import get_backend
from .config import GatewayConfig, load_config

log = logging.getLogger("local_agent.model_gateway")

_LOCK = threading.Lock()
_LAST: dict = {
    "last_plan": None,       # {"model", "chars", "tool_calls", "stop_reason", "at", "telemetry"}
    "last_fallback": None,   # {"kind", "detail", "at", "from_model"}
    "plans": 0,
    "fallbacks": 0,
}


def note_plan(*, model: str, chars: int, tool_calls: int, stop_reason: str | None,
              telemetry: dict | None = None) -> dict:
    entry = {"model": model, "chars": int(chars), "tool_calls": int(tool_calls),
             "stop_reason": stop_reason, "at": time.time(),
             "telemetry": dict((telemetry or {}).get("gateway") or {})}
    with _LOCK:
        _LAST["plans"] += 1
        _LAST["last_plan"] = entry
    log.info("model_gateway plan: %s chars=%d tool_calls=%d in=%s out=%s",
             model, chars, tool_calls,
             entry["telemetry"].get("input_tokens"), entry["telemetry"].get("output_tokens"))
    return entry


def note_fallback(kind: str, detail: str, *, from_model: str | None = None) -> dict:
    """Record that the cloud plan was unavailable; the turn continues locally."""
    entry = {"kind": kind, "detail": str(detail)[:300], "at": time.time(),
             "from_model": from_model}
    with _LOCK:
        _LAST["fallbacks"] += 1
        _LAST["last_fallback"] = entry
    log.warning("model_gateway: cloud plan unavailable (%s): %s (model %s); continuing locally",
                kind, entry["detail"], from_model)
    return entry


def status_snapshot(config: GatewayConfig | None = None) -> dict:
    cfg = config or load_config()
    snap = cfg.public_dict()
    with _LOCK:
        snap.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in _LAST.items()})
    try:
        snap["health"] = get_backend("anthropic", cfg).health()
    except Exception as exc:  # health must never break status()
        snap["health"] = {"backend": "anthropic", "error": str(exc)[:200]}
    return snap
