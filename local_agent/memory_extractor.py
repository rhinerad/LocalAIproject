#!/usr/bin/env python3
"""Asynchronous, privacy-limited extraction of durable operator facts."""
from __future__ import annotations

import json
import queue
import re
import threading
from typing import Any

import context_compactor
import memory
import ollama_client as oll
import router

MAX_PENDING_TURNS = 32
_PENDING: queue.Queue[tuple[str, str, str]] = queue.Queue(maxsize=MAX_PENDING_TURNS)
_WORKER: threading.Thread | None = None
_LOCK = threading.Lock()
_STOP = threading.Event()
_SENSITIVE = re.compile(r"(?i)(?:[a-z]:\\|\\\\|@|api[_ -]?key|token|password|secret)")
_CATEGORIES = frozenset({"preferences", "hardware", "workflow", "project"})
SCHEMA = {"type": "object", "properties": {"facts": {"type": "array", "items": {
    "type": "object", "properties": {
        "category": {"type": "string", "enum": sorted(_CATEGORIES)},
        "fact": {"type": "string"},
    }, "required": ["category", "fact"], "additionalProperties": False,
}}}, "required": ["facts"], "additionalProperties": False}


def _installed() -> bool:
    return context_compactor._installed()


def _clean(value: Any) -> list[tuple[str, str]]:
    if not isinstance(value, dict) or not isinstance(value.get("facts"), list):
        return []
    facts: list[tuple[str, str]] = []
    for row in value["facts"][:8]:
        if not isinstance(row, dict):
            continue
        category = str(row.get("category", ""))
        fact = " ".join(str(row.get("fact", "")).split())
        if category not in _CATEGORIES or not fact or len(fact) > 300 or _SENSITIVE.search(fact):
            continue
        facts.append((category, fact))
    return facts


def extract_and_remember(user_text: str, assistant_text: str) -> list[str]:
    """Extract only stable non-sensitive facts; return memory outcomes."""
    if not _installed() or router.chat_busy():
        return []
    try:
        text, _ = oll.chat([
            {"role": "system", "content":
             "Extract only durable, non-sensitive operator facts or explicit workflow "
             "preferences. Never store conversation summaries, temporary task state, "
             "file paths, names, credentials, private creative text, or assistant guesses. "
             "Return {facts: []} when nothing clearly qualifies."},
            {"role": "user", "content": f"Operator: {user_text[:4000]}\n\nAssistant: {assistant_text[:4000]}"},
        ], model=context_compactor.MODEL, host=router.CPU_HOST, timeout=120,
           keep_alive="0", options={"num_gpu": 0, "num_thread": router.CPU_THREAD_CAP, "num_ctx": 4096,
                                      "temperature": 0}, response_format=SCHEMA)
        return [memory.remember(fact, category) for category, fact in _clean(json.loads(text))]
    except Exception:
        return []


def enqueue_turn(conversation_id: str, user_text: str, assistant_text: str) -> bool:
    """Schedule post-turn extraction; never delay or fail the operator reply."""
    if not user_text or not assistant_text or not _installed():
        return False
    try:
        _PENDING.put_nowait((str(conversation_id)[:80], user_text, assistant_text))
        return True
    except queue.Full:
        return False


def _worker() -> None:
    while not _STOP.wait(1.0):
        if router.chat_busy():
            continue
        try:
            _cid, user_text, assistant_text = _PENDING.get_nowait()
        except queue.Empty:
            continue
        extract_and_remember(user_text, assistant_text)


def start_worker() -> None:
    global _WORKER
    with _LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _STOP.clear()
        _WORKER = threading.Thread(target=_worker, name="memory-extractor", daemon=True)
        _WORKER.start()
