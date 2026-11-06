#!/usr/bin/env python3
"""Durable local storage for tool output excluded from a live LLM context.

Artifacts are an internal context boundary, not a new execution or sharing
surface. They prevent a large directory listing, web page, or command result
from repeatedly consuming the active model window while retaining a local audit
copy for debugging and future purpose-built retrieval.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ARTIFACT_DIR = HERE / "runtime" / "artifacts"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def store(kind: str, text: object) -> str:
    """Persist one UTF-8 tool result and return its deterministic identifier."""
    value = str(text or "")
    digest = hashlib.sha1(value.encode("utf8", "replace")).hexdigest()
    artifact_id = f"artifact_{digest[:16]}"
    path = ARTIFACT_DIR / f"{artifact_id}.json"
    if not path.is_file():
        ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"id": artifact_id, "kind": str(kind)[:100], "sha1": digest,
                   "chars": len(value), "created_at": _utc(), "content": value}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf8")
        temporary.replace(path)
    return artifact_id


def prune_large_text(kind: str, text: object, limit: int = 2400,
                     source_label: str | None = None) -> str:
    """Return text for a small result or a local artifact pointer for a large one.

    ``source_label`` is included verbatim in the pointer when supplied, so the
    model can still see where oversized output came from even after the content
    is moved to local storage.  Pass the URL for ``fetch_url`` results, the
    file path for ``read_file``, the doc sources for ``search_docs``, etc.
    """
    if limit < 1:
        raise ValueError("limit must be positive")
    value = str(text or "")
    if len(value) <= limit:
        return value
    artifact_id = store(kind, value)
    source_part = f"; source={source_label}" if source_label else ""
    return (f"[{kind} output pruned{source_part}; artifact_id={artifact_id}; stored locally; "
            f"original_chars={len(value)}; sha1={hashlib.sha1(value.encode('utf8', 'replace')).hexdigest()}]")
