"""Plan-only model gateway: local Ollama executes every turn; a cloud model may
contribute a text plan for heavy prompts.

Public surface used by ``local_agent/router.py`` and ``local_agent/agent.py``:

    load_config()                          environment -> GatewayConfig (stdlib only)
    wants_cloud_plan(...)                  pure policy -> (bool, reason)
    request_plan(prompt, context, tools)   one plan-only call -> PlanText (a str) | None
                                           .plan_format "structured"|"text", .structured,
                                           .backend "api"|"claude_cli", .raw
    request_structured_plan(...)           the validated plan dict, or None
    parse_plan(text, tools) / render_plan  JSON plan -> dict -> numbered checklist
    build_plan_messages(...)               the exact messages that call sends
    status_snapshot()                      for router.status()
    note_fallback(kind, detail)            record a cloud->local fallback

Nothing in this package imports ``local_agent``; the dependency points one way.
The cloud model never answers a turn and is never given tools, on either plan
backend (Anthropic API or the headless Claude Code CLI, ``claude_cli.py``).
"""
from __future__ import annotations

from .config import DEFAULT_PLAN_MODEL, GatewayConfig, PlanTier, load_config
from .dispatch import note_fallback, note_plan, status_snapshot
from .events import CloudUnavailable, Completion, Done, TextDelta, ToolCalls
from .planning import (SYSTEM_TEMPLATE, PlanText, build_plan_messages, parse_plan,
                       render_plan, request_plan, request_structured_plan)
from .policy import wants_cloud_plan

__all__ = [
    "DEFAULT_PLAN_MODEL", "GatewayConfig", "PlanTier", "load_config",
    "note_fallback", "note_plan", "status_snapshot",
    "CloudUnavailable", "Completion", "Done", "TextDelta", "ToolCalls",
    "SYSTEM_TEMPLATE", "PlanText", "build_plan_messages", "parse_plan", "render_plan",
    "request_plan", "request_structured_plan",
    "wants_cloud_plan",
]
