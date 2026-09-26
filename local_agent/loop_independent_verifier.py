#!/usr/bin/env python3
"""Optional CPU-only evidence reviewer for loop-engineering completions.

This is deliberately a second opinion, not an autonomous repair agent.  It
gets only a compact goal, proposed-diff fingerprint, targeted test result, and
deterministic evidence.  It cannot access the project, tools, a conversation,
or the implementer's hidden reasoning; it cannot make a change or declare a
goal complete by itself.  Callers must opt in to a model call explicitly.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

import ollama_client as oll
import router

MODEL = os.environ.get("EQUAL_SHARES_LOOP_VERIFIER_MODEL", "huihui_ai/qwen3-abliterated:8b")
MAX_EVIDENCE_CHARS = 4_000
SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["supported", "needs_operator"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "evidence_ids", "reason"],
}


class IndependentVerificationError(ValueError):
    pass


def _compact(value: object, limit: int = MAX_EVIDENCE_CHARS) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value or "")
    return text[:limit] + ("…" if len(text) > limit else "")


def _parse(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise IndependentVerificationError("independent verifier returned invalid JSON") from exc
    if not isinstance(data, dict) or data.get("verdict") not in {"supported", "needs_operator"}:
        raise IndependentVerificationError("independent verifier returned an invalid verdict")
    ids = data.get("evidence_ids")
    if not isinstance(ids, list) or not all(isinstance(item, str) and len(item) <= 160 for item in ids):
        raise IndependentVerificationError("independent verifier returned invalid evidence IDs")
    reason = str(data.get("reason", "")).strip()
    if not reason or len(reason) > 800:
        raise IndependentVerificationError("independent verifier returned an invalid reason")
    return {"verdict": data["verdict"], "evidence_ids": ids[:12], "reason": reason}


def review(*, goal: dict[str, Any], repair: dict[str, Any] | None,
           test_result: dict[str, Any], deterministic_evidence: list[dict[str, Any]],
           allow_model_call: bool = False,
           chat_fn: Callable[..., tuple[str, list]] = oll.chat) -> dict[str, Any]:
    """Return a bounded evidence opinion, never an authorization.

    A caller must pass ``allow_model_call=True``.  Model or transport failures
    are returned as ``needs_operator``; they can never turn a deterministic
    pass into a completion claim.
    """
    if not allow_model_call:
        return {"verdict": "needs_operator", "reason": "independent model review was not explicitly enabled", "evidence_ids": []}
    packet = {
        "goal": {"id": str(goal.get("id", "")), "title": str(goal.get("title", ""))[:160],
                 "objective": str(goal.get("objective", ""))[:600]},
        "repair": {key: repair.get(key) for key in ("target_check", "diff_sha256", "content_sha256")} if isinstance(repair, dict) else None,
        "test_result": {key: test_result.get(key) for key in ("check", "passed", "returncode", "duration_seconds", "output")},
        "deterministic_evidence": deterministic_evidence[:12],
    }
    try:
        text, _ = chat_fn(
            [
                {"role": "system", "content": "You are an independent evidence reviewer. Review only the supplied evidence. Do not infer missing facts, propose edits, call tools, or reveal hidden reasoning. Return the requested JSON verdict. 'supported' is allowed only when the test passed and the supplied deterministic evidence supports the stated goal; otherwise use 'needs_operator'."},
                {"role": "user", "content": _compact(packet)},
            ],
            model=MODEL, host=router.CPU_HOST, timeout=120, keep_alive="0",
            options={"num_gpu": 0, "num_thread": router.CPU_THREAD_CAP, "num_ctx": 4096, "temperature": 0},
            response_format=SCHEMA,
        )
        return _parse(text)
    except (oll.OllamaUnavailable, oll.OllamaModelFailure, IndependentVerificationError) as exc:
        return {"verdict": "needs_operator", "reason": f"independent review unavailable: {str(exc)[:400]}", "evidence_ids": []}


def agreement(*, deterministic_passed: bool, independent: dict[str, Any]) -> dict[str, Any]:
    """Make the conservative policy decision from two visible evidence paths."""
    agreed = bool(deterministic_passed and independent.get("verdict") == "supported")
    return {
        "completion_allowed": agreed,
        "status": "agreement" if agreed else "needs_operator",
        "reason": "deterministic evidence and independent review agree" if agreed else "completion requires deterministic pass and independent support",
    }
