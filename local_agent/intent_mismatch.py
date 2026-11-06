#!/usr/bin/env python3
"""Operator-flagged intent-mismatch examples — local JSONL, nothing else.

A GUI button records one completed turn after the fact so vague-request
failures can be reviewed later. This does not train a model, change routing,
rewrite the reply, or enqueue encrypted feedback.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import store

LOG_PATH = Path(__file__).resolve().parent / "runtime" / "intent_mismatch.jsonl"
_LOCK = threading.Lock()

_KIND = "intent_mismatch"


def _assistant_index(messages: list, message_index) -> int:
    if message_index is None or message_index == "":
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "assistant":
                return i
        raise ValueError("conversation has no completed assistant response")
    try:
        idx = int(message_index)
    except (TypeError, ValueError) as exc:
        raise ValueError("message_index must be an integer") from exc
    if idx < 0 or idx >= len(messages) or messages[idx].get("role") != "assistant":
        raise ValueError("message_index does not point at an assistant response")
    return idx


def _prior_user(messages: list, assistant_index: int) -> dict:
    for i in range(assistant_index - 1, -1, -1):
        if messages[i].get("role") == "user":
            return messages[i]
    raise ValueError("no triggering user message")


def _route_fields(asst: dict, conv: dict) -> tuple[dict, bool]:
    """Per-message route if stored; otherwise conversation-level leftovers."""
    raw = asst.get("route")
    incomplete = not isinstance(raw, dict) or not raw
    route = dict(raw) if isinstance(raw, dict) else {}
    if not route.get("model"):
        pinned = conv.get("model")
        if pinned:
            route["model"] = pinned
    if not route.get("tier") and conv.get("last_tier"):
        route["tier"] = conv.get("last_tier")
        incomplete = True
    detail = route.get("detail") if isinstance(route.get("detail"), dict) else {}
    capability = route.get("capability") or detail.get("capability")
    return {
        "model": route.get("model"),
        "tier": route.get("tier"),
        "capability": capability,
        "reason": route.get("reason"),
        "host": route.get("host"),
        "backend": route.get("backend"),
    }, incomplete


def _tool_calls(asst: dict) -> list:
    tools = asst.get("tool_calls")
    if isinstance(tools, list):
        return tools
    evidence = asst.get("tool_evidence")
    return evidence if isinstance(evidence, list) else []


def capture(cid: str, message_index=None) -> dict:
    """Append one JSONL record for a completed turn. Does not mutate the chat."""
    cid = str(cid or "").strip()
    if not cid:
        raise ValueError("conversation id is required")
    conv = store.load(cid)
    if not conv:
        raise ValueError("conversation not found")
    messages = conv.get("messages") or []
    idx = _assistant_index(messages, message_index)
    asst = messages[idx]
    user = _prior_user(messages, idx)
    route, incomplete = _route_fields(asst, conv)
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "flagged_at": time.time(),
        "kind": _KIND,
        "conversation_id": cid,
        "assistant_index": idx,
        "user_message": user.get("content", ""),
        "user_at": user.get("at"),
        "assistant_message": asst.get("content", ""),
        "assistant_at": asst.get("at"),
        "tool_calls": _tool_calls(asst),
        "route": route,
        "route_incomplete": incomplete,
    }
    offset = _append(record)
    return {
        "ok": True,
        "kind": _KIND,
        "offset": offset,
        "path": "runtime/intent_mismatch.jsonl",
        "assistant_index": idx,
        "message": ("Saved this turn locally for later review. "
                    "The reply was not changed and nothing was sent off this machine."),
    }


def _append(record: dict) -> int:
    line = (json.dumps(record, ensure_ascii=False, default=str) + "\n").encode("utf-8")
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with LOG_PATH.open("ab") as fh:
                offset = fh.tell()
                fh.write(line)
                fh.flush()
        return offset
    except OSError as exc:
        raise ValueError(f"failed to write intent-mismatch log: {exc}") from exc
