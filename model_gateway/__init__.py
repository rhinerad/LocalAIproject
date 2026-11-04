"""Plan-only model gateway: local Ollama executes every turn; a cloud model may
contribute a text plan for heavy prompts.

Public surface used by ``local_agent/router.py`` and ``local_agent/agent.py``:

    load_config()                          environment -> GatewayConfig (stdlib only)
    wants_cloud_plan(...)                  pure policy -> (bool, reason)
    request_plan(prompt, context, tools)   one non-streaming cloud call -> str | None
    build_plan_messages(...)               the exact messages that call sends
    status_snapshot()                      for router.status()
    note_fallback(kind, detail)            record a cloud->local fallback

Nothing in this package imports ``local_agent``; the dependency points one way.
The cloud model never answers a turn and is never given tools.
"""
from __future__ import annotations

from .config import DEFAULT_PLAN_MODEL, GatewayConfig, PlanTier, load_config
from .dispatch import note_fallback, note_plan, status_snapshot
from .events import CloudUnavailable, Completion, Done, TextDelta, ToolCalls
from .planning import SYSTEM_TEMPLATE, build_plan_messages, request_plan
from .policy import wants_cloud_plan

__all__ = [
    "DEFAULT_PLAN_MODEL", "GatewayConfig", "PlanTier", "load_config",
    "note_fallback", "note_plan", "status_snapshot",
    "CloudUnavailable", "Completion", "Done", "TextDelta", "ToolCalls",
    "SYSTEM_TEMPLATE", "build_plan_messages", "request_plan",
    "wants_cloud_plan",
]
