"""Call-time glue used by ``local_agent/ollama_client.py``.

``stream_for_host`` is what the Ollama client calls when ``Decision.host``
starts with ``anthropic://``. It resolves the adapter from the host prefix,
streams provider-neutral events, and records the outcome for ``status()``.

The gateway never decides *whether* a turn goes to the cloud here; that is
``router.decide()`` via ``policy.choose_cloud_tier``. This module only knows
how to talk to the chosen provider.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Iterator

from .adapters import get_backend
from .config import CLOUD_HOST_PREFIX, GatewayConfig, is_cloud_host, load_config
from .events import CloudUnavailable, Done, TextDelta, ToolCalls

log = logging.getLogger("local_agent.model_gateway")

_LOCK = threading.Lock()
_LAST: dict = {
    "last_call": None,       # {"model", "stop_reason", "ok", "at", "telemetry"}
    "last_fallback": None,   # {"kind", "detail", "at", "from_model"}
    "calls": 0,
    "fallbacks": 0,
}


def backend_name_for_host(host: str) -> str:
    if not is_cloud_host(host):
        raise CloudUnavailable("disabled", f"{host!r} is not a gateway host")
    return "anthropic"  # the prefix is the provider; extend here for a second vendor


def stream_for_host(
    host: str,
    *,
    model: str,
    messages: list[dict],
    tools: list[dict] | None = None,
    response_format: dict | str | None = None,
    options: dict | None = None,
    should_stop: Callable[[], bool] | None = None,
    config: GatewayConfig | None = None,
) -> Iterator[TextDelta | ToolCalls | Done]:
    cfg = config or load_config()
    backend = get_backend(backend_name_for_host(host), cfg)
    with _LOCK:
        _LAST["calls"] += 1
    try:
        for piece in backend.stream(model=model, messages=messages, tools=tools,
                                    response_format=response_format, options=options,
                                    should_stop=should_stop):
            if isinstance(piece, Done):
                with _LOCK:
                    _LAST["last_call"] = {
                        "model": piece.model, "stop_reason": piece.stop_reason,
                        "ok": True, "at": time.time(),
                        "telemetry": dict(piece.telemetry.get("gateway", {})),
                    }
            yield piece
    except CloudUnavailable as exc:
        note_fallback(exc.kind, exc.detail, from_model=model)
        raise


def note_fallback(kind: str, detail: str, *, from_model: str | None = None) -> dict:
    """Record a cloud->local fallback so the status badge and logs show it."""
    entry = {"kind": kind, "detail": str(detail)[:300], "at": time.time(),
             "from_model": from_model}
    with _LOCK:
        _LAST["fallbacks"] += 1
        _LAST["last_fallback"] = entry
        _LAST["last_call"] = {"model": from_model, "stop_reason": None, "ok": False,
                              "at": entry["at"], "telemetry": {}}
    log.warning("model_gateway fallback to local Ollama: %s — %s (from %s)",
                kind, entry["detail"], from_model)
    return entry


def fallback_note(kind: str, detail: str, local_model: str | None) -> str:
    """One-line operator note for the turn on which a fallback happened."""
    target = local_model or "the local Ollama tier"
    return f"cloud tier unavailable ({kind}); continuing this turn on {target}"


def status_snapshot(config: GatewayConfig | None = None) -> dict:
    cfg = config or load_config()
    snap = cfg.public_dict()
    with _LOCK:
        snap.update({k: (dict(v) if isinstance(v, dict) else v) for k, v in _LAST.items()})
    try:
        snap["health"] = get_backend("anthropic", cfg).health()
    except Exception as exc:  # health must never break status()
        snap["health"] = {"backend": "anthropic", "error": str(exc)[:200]}
    snap["host"] = CLOUD_HOST_PREFIX + cfg.netloc
    return snap
