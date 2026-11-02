"""Unified model gateway: local Ollama tiers plus an optional Anthropic tier.

Public surface used by ``local_agent/router.py`` and ``local_agent/ollama_client.py``:

    load_config()                      environment -> GatewayConfig (stdlib only)
    is_cloud_host(host)                Decision.host starts with "anthropic://"
    is_cloud_pin(model)                picker alias or literal claude-* id
    choose_cloud_tier(...)             pure policy -> TierChoice | Refusal | None
    stream_for_host(host, ...)         call-time dispatch -> TextDelta/ToolCalls/Done
    note_fallback(kind, detail)        record a cloud->local fallback
    fallback_note(kind, detail, model) operator-facing one-liner for that turn
    status_snapshot()                  for router.status()
    picker_entries(config)             chat_models() rows for the GUI picker

Nothing in this package imports ``local_agent``; the dependency points one way.
"""
from __future__ import annotations

from .config import (
    CLOUD_HOST_PREFIX,
    PIN_CLOUD_FAST,
    PIN_CLOUD_HEAVY,
    TIER_CLOUD_FAST,
    TIER_CLOUD_HEAVY,
    TIER_LOCAL_CPU,
    TIER_LOCAL_GPU,
    GatewayConfig,
    is_cloud_host,
    is_cloud_pin,
    load_config,
)
from .dispatch import fallback_note, note_fallback, status_snapshot, stream_for_host
from .events import CloudUnavailable, Done, TextDelta, ToolCalls
from .policy import Refusal, TierChoice, choose_cloud_tier

__all__ = [
    "CLOUD_HOST_PREFIX", "PIN_CLOUD_FAST", "PIN_CLOUD_HEAVY",
    "TIER_CLOUD_FAST", "TIER_CLOUD_HEAVY", "TIER_LOCAL_CPU", "TIER_LOCAL_GPU",
    "GatewayConfig", "is_cloud_host", "is_cloud_pin", "load_config",
    "fallback_note", "note_fallback", "status_snapshot", "stream_for_host",
    "CloudUnavailable", "Done", "TextDelta", "ToolCalls",
    "Refusal", "TierChoice", "choose_cloud_tier", "picker_entries",
]


def picker_entries(config: GatewayConfig | None = None) -> list[dict]:
    """Rows for ``router.chat_models()``: shown only when the cloud tier is on."""
    cfg = config or load_config()
    if not cfg.cloud_enabled:
        return []
    ready = cfg.credential_present
    why = "" if ready else "set ANTHROPIC_API_KEY (model_gateway/.env) to enable"
    rows = []
    for pin, tier, blurb in (
        (PIN_CLOUD_HEAVY, cfg.heavy, "cloud, heavy reasoning"),
        (PIN_CLOUD_FAST, cfg.fast, "cloud, fast continuation"),
    ):
        rows.append({
            "name": pin,
            "cpu": False,
            "gpu": False,
            "cloud": True,
            "available": ready,
            "gpu_only": False,
            "kind": "chat",
            "backend": "anthropic",
            "label": f"{pin} → {tier.model} ({blurb}, effort {tier.effort})",
            "setup_hint": "Routes this chat through the Anthropic API; no local VRAM is used.",
            **({} if ready else {"unavailable_reason": why}),
        })
    return rows
