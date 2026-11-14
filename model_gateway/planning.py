"""Plan-only cloud call: one non-streaming request that returns a plan.

``request_plan`` is the only function the agent calls. Contract:

* exactly one planning call per backend tried (``MODEL_GATEWAY_PLAN_BACKEND``):
  ``api`` = one ``messages.create`` to the configured planning model;
  ``claude_cli`` = one headless ``claude -p`` with every tool disabled
  (``claude_cli.py``); ``auto`` = the CLI first, the API if the CLI fails
* ``tools=None`` and no ``tool_choice`` on the API; ``--tools ""`` on the CLI:
  the cloud model cannot act
* ``max_tokens`` capped by ``MODEL_GATEWAY_PLAN_MAX_TOKENS`` (default 3000)
* sends only the operator prompt and the compact text summary the caller
  supplies; never file contents beyond what the prompt already holds
* returns ``None`` on any failure and logs it; never raises into the agent

The planning model is asked for a structured plan (one JSON object, the
"schematic"). ``parse_plan`` validates it and ``render_plan`` turns it into a
numbered checklist for the local model. The return value is a ``PlanText``:
a ``str`` (so every existing caller keeps working) holding the rendered
checklist, or the model's raw text when it did not return valid JSON. A plan
is never dropped because it failed to parse. Extra attributes:

    .plan_format   "structured" | "text"
    .structured    the validated dict, or None
    .raw           the model's text exactly as returned
    .backend       "api" | "claude_cli"
    .model         the model that wrote it
"""
from __future__ import annotations

import json
import logging
import re
from typing import Iterable

from . import dispatch
from .adapters import get_backend
from .config import GatewayConfig, load_config
from .events import CloudUnavailable

log = logging.getLogger("local_agent.model_gateway")

PLAN_KEYS = ("goal", "assumptions", "steps", "acceptance", "stop_if")
STEP_KEYS = ("id", "action", "files_read", "files_change", "commands", "tools",
             "expected", "verify")

SYSTEM_TEMPLATE = (
    "You write plans for a local agent that has these tools: {names}. "
    "Do not perform the task. Return only a plan the local agent will execute.\n"
    "Reply with exactly one JSON object and nothing else (no prose, no code fences):\n"
    '{{"goal": "one sentence", '
    '"assumptions": ["..."], '
    '"steps": [{{"id": 1, "action": "what to do", '
    '"files_read": ["path"], "files_change": ["path"], '
    '"commands": ["exact command"], "tools": ["tool_name"], '
    '"expected": "what the step should produce", '
    '"verify": "concrete check that proves the step worked"}}], '
    '"acceptance": ["criterion for the whole task"], '
    '"stop_if": ["condition under which the agent must stop and report instead of guessing"]}}\n'
    "Rules: number steps 1, 2, 3 in execution order; \"tools\" may only name tools from "
    "the list above; \"commands\" holds exact commands or is empty; use empty lists where "
    "nothing applies; every step needs a concrete \"verify\". No code longer than needed "
    "to specify a step."
)
MAX_PROMPT_CHARS = 12_000
MAX_CONTEXT_CHARS = 3_000
MAX_TOOL_NAMES = 120
MAX_STEPS = 40
MAX_FIELD_CHARS = 1_500
MAX_LIST_ITEMS = 20

_FENCE = re.compile(r"```[A-Za-z0-9_-]*\s*\n?(.*?)```", re.S)


class PlanText(str):
    """The plan as text, plus how it was produced. Compares equal to the text."""

    def __new__(cls, text: str, *, raw: str = "", structured: dict | None = None,
                plan_format: str = "text", backend: str = "api", model: str = ""):
        obj = super().__new__(cls, text)
        obj.raw = raw or str(text)
        obj.structured = structured
        obj.plan_format = plan_format
        obj.backend = backend
        obj.model = model
        return obj


def _clean_names(tool_names: Iterable[str]) -> list[str]:
    return [str(n).strip() for n in (tool_names or ()) if str(n).strip()][:MAX_TOOL_NAMES]


def build_plan_messages(prompt: str, context_summary: str = "",
                        tool_names: Iterable[str] = ()) -> tuple[str, list[dict]]:
    """Return ``(system_text, ollama_shaped_messages)`` for the planning call."""
    names = _clean_names(tool_names)
    system = SYSTEM_TEMPLATE.format(names=", ".join(names) if names else "(no tools)")
    user = str(prompt or "").strip()[:MAX_PROMPT_CHARS]
    summary = " ".join(str(context_summary or "").split())[:MAX_CONTEXT_CHARS]
    parts = []
    if summary:
        parts.append("Conversation so far (compact summary, not evidence):\n" + summary)
    parts.append("Operator request:\n" + user)
    return system, [{"role": "system", "content": system},
                    {"role": "user", "content": "\n\n".join(parts)}]


# ── structured plan: parse, validate, render ────────────────────────────────

def _json_candidates(text: str) -> list[str]:
    out = [m.group(1).strip() for m in _FENCE.finditer(text)]
    out.append(text.strip())
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        out.append(text[start:end + 1])
    return [c for c in out if c]


def _s(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return " ".join(str(value).split())[:MAX_FIELD_CHARS]


def _list(value) -> list[str]:
    if value is None or value == "":
        return []
    if not isinstance(value, (list, tuple)):
        value = [value]
    return [s for s in (_s(v) for v in value) if s][:MAX_LIST_ITEMS]


def _first(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def parse_plan(text: str, tool_names: Iterable[str] | None = None) -> dict | None:
    """Validate a structured plan. Returns the normalised dict, or ``None``.

    Tolerates code fences and prose around the object. ``tools`` in each step
    are restricted to ``tool_names`` (when given); dropped names are listed
    under ``"dropped_tools"``. Steps are renumbered 1..n in the given order.
    """
    if not text or not str(text).strip():
        return None
    data = None
    for chunk in _json_candidates(str(text)):
        try:
            candidate = json.loads(chunk)
        except ValueError:
            continue
        if not isinstance(candidate, dict):
            continue
        if isinstance(candidate.get("plan"), dict) and "steps" not in candidate:
            candidate = candidate["plan"]
        if isinstance(candidate.get("steps"), list):
            data = candidate
            break
    if data is None:
        return None
    raw_steps = data["steps"]
    allowed = None if tool_names is None else set(_clean_names(tool_names))
    dropped: list[str] = []
    steps: list[dict] = []
    for raw in raw_steps[:MAX_STEPS]:
        if isinstance(raw, str):
            raw = {"action": raw}
        if not isinstance(raw, dict):
            continue
        action = _s(_first(raw, "action", "step", "description", "title", "do"))
        if not action:
            continue
        tools = _list(_first(raw, "tools", "tool"))
        if allowed is not None:
            for t in tools:
                if t not in allowed and t not in dropped:
                    dropped.append(t)
            tools = [t for t in tools if t in allowed]
        steps.append({
            "id": len(steps) + 1,
            "action": action,
            "files_read": _list(_first(raw, "files_read", "read", "files")),
            "files_change": _list(_first(raw, "files_change", "files_changed", "change", "modify")),
            "commands": _list(_first(raw, "commands", "command", "cmd")),
            "tools": tools,
            "expected": _s(_first(raw, "expected", "expected_result", "result", "output")),
            "verify": _s(_first(raw, "verify", "verification", "check", "validate")),
        })
    if not steps:
        return None
    plan = {
        "goal": _s(_first(data, "goal", "objective", "summary")),
        "assumptions": _list(data.get("assumptions")),
        "steps": steps,
        "acceptance": _list(_first(data, "acceptance", "acceptance_criteria", "done_when")),
        "stop_if": _list(_first(data, "stop_if", "stop_conditions", "escalation",
                                "escalate_if", "stop")),
    }
    if dropped:
        plan["dropped_tools"] = dropped
    return plan


def render_plan(plan: dict) -> str:
    """Numbered checklist the local model can follow step by step."""
    lines: list[str] = []
    if plan.get("goal"):
        lines.append("Goal: " + plan["goal"])
    if plan.get("assumptions"):
        lines.append("Assumptions (check them, do not trust them):")
        lines += ["- " + a for a in plan["assumptions"]]
    lines.append("Steps (in order; run each Verify check before the next step):")
    for st in plan.get("steps") or []:
        lines.append(f"{st['id']}. {st['action']}")
        for label, key in (("Read", "files_read"), ("Change", "files_change"),
                           ("Tools", "tools")):
            if st.get(key):
                lines.append(f"   {label}: " + ", ".join(st[key]))
        for cmd in st.get("commands") or []:
            lines.append("   Run: " + cmd)
        if st.get("expected"):
            lines.append("   Expect: " + st["expected"])
        if st.get("verify"):
            lines.append("   Verify: " + st["verify"])
    if plan.get("acceptance"):
        lines.append("Done when:")
        lines += ["- " + a for a in plan["acceptance"]]
    if plan.get("stop_if"):
        lines.append("Stop and report instead of guessing if:")
        lines += ["- " + a for a in plan["stop_if"]]
    if plan.get("dropped_tools"):
        lines.append("(Planner named tools you do not have, removed: "
                     + ", ".join(plan["dropped_tools"]) + ")")
    return "\n".join(lines)


def to_plan_text(text: str, tool_names: Iterable[str] | None = None, *,
                 backend: str = "api", model: str = "") -> PlanText:
    """Structured checklist when ``text`` parses, the raw text otherwise."""
    raw = str(text or "").strip()
    plan = parse_plan(raw, tool_names)
    if plan is not None:
        return PlanText(render_plan(plan), raw=raw, structured=plan,
                        plan_format="structured", backend=backend, model=model)
    return PlanText(raw, raw=raw, structured=None, plan_format="text",
                    backend=backend, model=model)


# ── backends ────────────────────────────────────────────────────────────────

def _backend_order(cfg: GatewayConfig) -> list[str]:
    mode = getattr(cfg, "plan_backend", "api")
    if mode == "claude_cli":
        return ["claude_cli"] if cfg.cli_available else []
    if mode == "auto":
        order = []
        if cfg.cli_available:
            order.append("claude_cli")
        if cfg.api_available:
            order.append("api")
        return order
    return ["api"] if cfg.credential_present else []


def _call(name: str, cfg: GatewayConfig, system: str, messages: list[dict], backend, cli_runner):
    if name == "claude_cli":
        from . import claude_cli
        kwargs = {"runner": cli_runner} if cli_runner is not None else {}
        return claude_cli.run_plan(cfg, system, messages[-1]["content"], **kwargs), cfg.claude_cli_model
    be = backend or get_backend("anthropic", cfg)
    return be.complete(
        model=cfg.plan.model, messages=messages, tools=None, response_format=None,
        options={"effort": cfg.plan.effort, "max_tokens": cfg.plan.max_tokens}), cfg.plan.model


def request_plan(prompt: str, context_summary: str = "", tool_names: Iterable[str] = (),
                 *, config: GatewayConfig | None = None, backend=None,
                 cli_runner=None) -> PlanText | None:
    cfg = config or load_config()
    if not cfg.planning_available:
        return None
    if not str(prompt or "").strip():
        return None
    names = _clean_names(tool_names)
    system, messages = build_plan_messages(prompt, context_summary, names)
    for name in _backend_order(cfg):
        from_model = cfg.claude_cli_model if name == "claude_cli" else cfg.plan.model
        try:
            result, from_model = _call(name, cfg, system, messages, backend, cli_runner)
        except CloudUnavailable as exc:
            dispatch.note_fallback(exc.kind, f"[{name}] {exc.detail}", from_model=from_model)
            continue
        except Exception as exc:  # contract: never raise into the agent
            dispatch.note_fallback("error", f"[{name}] {type(exc).__name__}: {str(exc)[:200]}",
                                   from_model=from_model)
            log.exception("model_gateway plan request failed unexpectedly")
            continue
        text = (result.text or "").strip()
        if result.calls:
            # tools=None / --tools "" make this impossible; a proxy could
            # still echo something. Never act on it.
            log.warning("model_gateway: planning model returned %d tool call(s); ignored",
                        len(result.calls))
        if not text:
            dispatch.note_fallback("empty", f"[{name}] planning model returned no text",
                                   from_model=result.model)
            continue
        plan = to_plan_text(text, names, backend=name, model=result.model)
        dispatch.note_plan(model=result.model, chars=len(text), tool_calls=len(result.calls),
                           stop_reason=result.stop_reason, telemetry=result.telemetry,
                           backend=name, plan_format=plan.plan_format)
        return plan
    return None


def request_structured_plan(prompt: str, context_summary: str = "",
                            tool_names: Iterable[str] = (), **kwargs) -> dict | None:
    """The validated plan dict, or ``None`` (no plan, or the plan was not structured)."""
    plan = request_plan(prompt, context_summary, tool_names, **kwargs)
    return plan.structured if plan is not None else None
