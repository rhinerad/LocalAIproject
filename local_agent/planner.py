#!/usr/bin/env python3
"""Structured, non-executing plan proposals for substantive local-agent work.

The planner is intentionally a small seam rather than an autonomous agent.  It
asks the selected local Ollama model for a JSON checklist, validates every field
and stores only the resulting operator-visible plan. ``agent.py`` still owns the
tool loop and ``tools.py`` remains the only execution boundary.
"""
from __future__ import annotations

import json
import re
from typing import Any

import ollama_client as oll
import router

MAX_STEPS = 6
_TEXT_RE = re.compile(r"\S")
_ACTION_WORDS = re.compile(
    r"\b(?:delete|remove|overwrite|rename|move|format|download|install|"
    r"render|start|stop|run|execute|shell|powershell|cmd|write|edit|create)\b", re.I)

PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "goal": {"type": "string", "maxLength": 420},
        "steps": {
            "type": "array", "minItems": 2, "maxItems": MAX_STEPS,
            "items": {
                "type": "object", "additionalProperties": False,
                "properties": {
                    "title": {"type": "string", "maxLength": 180},
                    "success_condition": {"type": "string", "maxLength": 180},
                },
                "required": ["title", "success_condition"],
            },
        },
        "needs_operator_decision": {"type": "boolean"},
    },
    "required": ["goal", "steps", "needs_operator_decision"],
}


def _clean(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def validate_plan(value: Any, operator_goal: str) -> dict | None:
    """Accept a narrow inert plan shape; reject instructions masquerading as tools."""
    if not isinstance(value, dict) or not isinstance(value.get("steps"), list):
        return None
    steps = []
    for item in value["steps"][:MAX_STEPS]:
        if not isinstance(item, dict):
            return None
        title = _clean(item.get("title"), 180)
        success = _clean(item.get("success_condition"), 180)
        if not (_TEXT_RE.search(title) and _TEXT_RE.search(success)):
            return None
        # A checklist must not embed an operation.  It may say “verify render
        # preflight”, but it cannot direct the harness to render/start/delete.
        if _ACTION_WORDS.search(title) or _ACTION_WORDS.search(success):
            return None
        steps.append({"title": title, "success_condition": success})
    if len(steps) < 2:
        return None
    return {
        "goal": _clean(value.get("goal") or operator_goal, 420),
        "steps": steps,
        "needs_operator_decision": bool(value.get("needs_operator_decision", False)),
        "source": "structured_local_model",
    }


def propose(operator_goal: str, checkpoint: str = "", prefer: str = "auto",
            model: str | None = None) -> tuple[dict | None, str]:
    """Request a JSON plan. Returns ``(plan, reason)`` and never raises for bad JSON."""
    route = router.decide(prefer, model=model)
    if not route.model:
        return None, "no eligible local model"
    message = (
        "Create a short, operator-visible checklist for this task. Do not reason aloud. "
        "Do not call tools, issue commands, choose paths, start renders, install, delete, "
        "or claim that a step succeeded. Use neutral verification language. "
        "Return only JSON matching the supplied schema.\n\n"
        f"Operator task:\n{_clean(operator_goal, 900)}"
    )
    if checkpoint:
        message += "\n\nExisting trusted checkpoint:\n" + _clean(checkpoint, 900)
    opts = route.options()
    # A plan proposal should be short, stable, and never turn on a model's
    # optional thinking stream. It runs sequentially inside agent.answer().
    opts.update({"temperature": 0.0, "num_predict": 500})
    try:
        text, _calls = oll.chat([
            {"role": "system", "content":
             "You are a planner. Return a compact JSON plan only; no markdown."},
            {"role": "user", "content": message},
        ], model=route.model, host=route.host, options=opts,
           response_format=PLAN_SCHEMA, timeout=180, keep_alive=0)
        raw = json.loads(text)
    except (oll.OllamaUnavailable, oll.OllamaModelFailure, ValueError,
            json.JSONDecodeError, TypeError) as exc:
        return None, f"planner unavailable or invalid: {str(exc)[:180]}"
    plan = validate_plan(raw, operator_goal)
    return (plan, "structured plan accepted") if plan else (None, "planner output failed validation")
