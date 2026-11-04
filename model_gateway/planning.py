"""Plan-only cloud call: one non-streaming request that returns a text plan.

``request_plan`` is the only function the agent calls. Contract:

* exactly one ``messages.create`` to the configured planning model
* ``tools=None`` and no ``tool_choice``: the cloud model cannot act
* ``max_tokens`` capped by ``MODEL_GATEWAY_PLAN_MAX_TOKENS`` (default 1500)
* sends only the operator prompt and the compact text summary the caller
  supplies; never file contents beyond what the prompt already holds
* returns ``None`` on any failure and logs it; never raises into the agent
"""
from __future__ import annotations

import logging
from typing import Iterable

from . import dispatch
from .adapters import get_backend
from .config import GatewayConfig, load_config
from .events import CloudUnavailable

log = logging.getLogger("local_agent.model_gateway")

SYSTEM_TEMPLATE = (
    "Return a numbered step-by-step plan for a local agent with these tools: "
    "{names}. Do not perform the task. No code longer than needed to specify a "
    "step."
)
MAX_PROMPT_CHARS = 12_000
MAX_CONTEXT_CHARS = 3_000
MAX_TOOL_NAMES = 120


def build_plan_messages(prompt: str, context_summary: str = "",
                        tool_names: Iterable[str] = ()) -> tuple[str, list[dict]]:
    """Return ``(system_text, ollama_shaped_messages)`` for the planning call."""
    names = [str(n).strip() for n in tool_names if str(n).strip()][:MAX_TOOL_NAMES]
    system = SYSTEM_TEMPLATE.format(names=", ".join(names) if names else "(no tools)")
    user = str(prompt or "").strip()[:MAX_PROMPT_CHARS]
    summary = " ".join(str(context_summary or "").split())[:MAX_CONTEXT_CHARS]
    parts = []
    if summary:
        parts.append("Conversation so far (compact summary, not evidence):\n" + summary)
    parts.append("Operator request:\n" + user)
    return system, [{"role": "system", "content": system},
                    {"role": "user", "content": "\n\n".join(parts)}]


def request_plan(prompt: str, context_summary: str = "", tool_names: Iterable[str] = (),
                 *, config: GatewayConfig | None = None, backend=None) -> str | None:
    cfg = config or load_config()
    if not cfg.planning_available:
        return None
    if not str(prompt or "").strip():
        return None
    _system, messages = build_plan_messages(prompt, context_summary, tool_names)
    try:
        be = backend or get_backend("anthropic", cfg)
        result = be.complete(
            model=cfg.plan.model, messages=messages, tools=None, response_format=None,
            options={"effort": cfg.plan.effort, "max_tokens": cfg.plan.max_tokens})
    except CloudUnavailable as exc:
        dispatch.note_fallback(exc.kind, exc.detail, from_model=cfg.plan.model)
        return None
    except Exception as exc:  # contract: never raise into the agent
        dispatch.note_fallback("error", f"{type(exc).__name__}: {str(exc)[:200]}",
                               from_model=cfg.plan.model)
        log.exception("model_gateway plan request failed unexpectedly")
        return None
    text = (result.text or "").strip()
    dispatch.note_plan(model=result.model, chars=len(text), tool_calls=len(result.calls),
                       stop_reason=result.stop_reason, telemetry=result.telemetry)
    if result.calls:
        # tools=None makes this impossible on the official API; a proxy could
        # still echo something. Never act on it.
        log.warning("model_gateway: planning model returned %d tool call(s); ignored",
                    len(result.calls))
    if not text:
        dispatch.note_fallback("empty", "planning model returned no text",
                               from_model=result.model)
        return None
    return text
