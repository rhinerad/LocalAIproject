#!/usr/bin/env python3
"""Explicit user feedback and opt-in durable learning for the local agent.

Silence is never approval. A response can be marked helpful/corrected for an
audit trail, but only a deliberate ``remembered`` submission writes a reusable
rule into persistent memory. Raw assistant text is never copied to the ledger.
"""
from __future__ import annotations

import re

import feedback_manager
import exemplar_lifecycle
import memory
import store

_VERDICTS = frozenset({"helpful", "corrected", "remembered"})
_UNSAFE_RULE = re.compile(
    r"\b(?:ignore (?:all |the )?(?:rules|safeguards)|bypass|disable (?:all )?"
    r"(?:safeguards|validation)|arbitrary shell|bind .*0\.0\.0\.0|"
    r"delete (?:evidence|uploads|manifest))\b", re.I)


def _short(value: object, limit: int = 600) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _last_assistant(cid: str) -> str:
    conversation = store.load(cid)
    if not conversation:
        raise ValueError("conversation not found")
    for message in reversed(conversation.get("messages", [])):
        if message.get("role") == "assistant":
            return str(message.get("content", ""))
    raise ValueError("conversation has no completed assistant response")


def _last_exemplar_ids(cid: str) -> list[str]:
    conversation = store.load(cid) or {}
    for message in reversed(conversation.get("messages", [])):
        if message.get("role") == "assistant":
            return [str(value) for value in message.get("retrieved_exemplar_ids", [])
                    if str(value).startswith("stage_")]
    return []


def submit(cid: str, verdict: str, correction: str = "", *,
           mode: str = "rule_only", category: str = "",
           exemplar_ids: list[str] | None = None) -> dict:
    """Record explicit feedback; only ``remembered`` creates durable memory."""
    verdict = str(verdict or "").strip().lower()
    if verdict not in _VERDICTS:
        raise ValueError(f"unknown feedback verdict {verdict!r}")
    _last_assistant(cid)  # Preserve the existing completed-turn guard.
    rule = _short(correction, 600)
    if verdict == "remembered":
        if not rule:
            raise ValueError("a reusable rule is required before anything is remembered")
        if _UNSAFE_RULE.search(rule):
            raise ValueError("that rule would weaken a safety boundary and was not saved")
        memory_result = memory.remember(rule, "user-confirmed rule")
    else:
        memory_result = "not promoted to persistent memory"
    rating = "negative" if verdict == "corrected" else "positive"
    record = feedback_manager.build_record(
        cid, rating=rating, distilled_rule=rule if verdict == "remembered" else "",
        mode=mode, category=category)
    attributed_ids = exemplar_ids or _last_exemplar_ids(cid)
    if attributed_ids:
        exemplar_lifecycle.record_attribution(record["message_id"], attributed_ids)
        exemplar_lifecycle.update_scores(record["message_id"], rating)
    feedback_manager.enqueue(record)
    return {"ok": True, "verdict": verdict, "memory": memory_result,
            "message": ("Saved as a reusable rule; encrypted feedback is queued for idle processing."
                        if verdict == "remembered" else
                        "Feedback queued for encrypted idle-only processing; nothing was added to persistent memory."),
            "feedback_id": record["id"], "pending_encryption": True}
