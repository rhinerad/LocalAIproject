"""Persistent operator facts across conversations.

Stored in local_agent/memory.json:
  { "facts": [...], "_forgotten": [...] }

Each fact: { "id": N, "category": "...", "text": "...", "fp": "...", "added": "YYYY-MM-DD" }

recall() is called once per system prompt build and injected under
# What I know about this operator. Cap is 1 KB; if exceeded, the
block includes a warning so the operator knows to prune deliberately.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import atomic_write_text

_STORE = Path(__file__).resolve().parent / "memory.json"
_CAP_BYTES = 1024
_OMITTED_NOTICE = "\n\n[Additional durable memories remain available via list_memory.]"


def _load() -> dict:
    try:
        return json.loads(_STORE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"facts": [], "_forgotten": []}
    except Exception:
        return {"facts": [], "_forgotten": []}


def _save(data: dict) -> None:
    atomic_write_text(_STORE, json.dumps(data, indent=2, ensure_ascii=False))


def _fp(text: str) -> str:
    return hashlib.sha1(text.strip().lower().encode()).hexdigest()[:12]


def remember(fact: str, category: str = "general") -> str:
    """Append a fact. No-op if the same text is already known."""
    fact = fact.strip()
    if not fact:
        return "nothing to remember"
    data = _load()
    fp = _fp(fact)
    fact_lower = fact.lower()
    for f in data["facts"]:
        # Match by fingerprint (fast) or by text (catches seed data without fp)
        if f.get("fp") == fp or f.get("text", "").strip().lower() == fact_lower:
            return f"already known (id {f['id']})"
    next_id = max(
        (f["id"] for f in data["facts"] + data["_forgotten"]), default=-1
    ) + 1
    data["facts"].append({
        "id": next_id,
        "category": category,
        "text": fact,
        "fp": fp,
        "added": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
    _save(data)
    return f"remembered (id {next_id})"


def recall(include_project: bool = True) -> str:
    """Return the scope-appropriate active facts for the system prompt.

    Project memories are valuable while working in Equal Shares, but injecting
    them into every ordinary conversation makes a small local model assume that
    unrelated creative or ComfyUI work belongs to the film. The full list stays
    available through ``list_memory``; this only controls the automatic prompt.

    Returns an empty string if no facts exist (so system_prompt can skip
    the section entirely rather than emitting an empty header).
    """
    facts = _load().get("facts", [])
    # Workflow rows are ephemeral job-state, not durable operator policy.
    facts = [fact for fact in facts if fact.get("category") != "workflow"]
    if not include_project:
        facts = [fact for fact in facts
                 if fact.get("category") not in {"project", "project state"}]
    if not facts:
        return ""
    # Keep the system prompt bounded. The old implementation emitted every fact
    # and merely *reported* that it exceeded the cap, which defeated the cap and
    # contributed to context churn. Facts stay on disk and remain available to
    # list_memory; this only selects the most useful always-on subset.
    priority = {"preferences": 0, "user-confirmed rule": 0, "local-agent GPU rule": 1,
                "hardware": 2, "goal": 3, "project": 4, "general": 5}
    ordered = sorted(facts, key=lambda f: (priority.get(f.get("category", "general"), 5),
                                           -int(f.get("id", 0))))
    selected: list[dict] = []
    used = 0
    for fact in ordered:
        text = str(fact.get("text", "")).strip()
        line_bytes = len((f"[{fact.get('category', 'general')}]\n- {text}\n").encode())
        # Reserve space for the omission notice whenever another fact exists.
        reserve = len(_OMITTED_NOTICE.encode()) if len(selected) + 1 < len(facts) else 0
        if text and used + line_bytes + reserve <= _CAP_BYTES:
            selected.append(fact)
            used += line_bytes
    by_cat: dict[str, list[str]] = {}
    for f in selected:
        by_cat.setdefault(f.get("category", "general"), []).append(f["text"])
    lines: list[str] = []
    for cat, texts in by_cat.items():
        lines.append(f"[{cat}]")
        for t in texts:
            lines.append(f"- {t}")
    block = "\n".join(lines)
    if len(selected) < len(facts):
        block += _OMITTED_NOTICE
    return block


def forget(index: int) -> str:
    """Move a fact to _forgotten. Never hard-deletes."""
    data = _load()
    fact = next((f for f in data["facts"] if f["id"] == index), None)
    if fact is None:
        ids = [f["id"] for f in data["facts"]]
        return f"no fact with id {index}. Active ids: {ids}"
    data["facts"].remove(fact)
    fact["forgotten"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    data["_forgotten"].append(fact)
    _save(data)
    return f"forgotten (id {index}): {fact['text'][:80]}"


def list_facts() -> list[dict]:
    """All active facts as dicts, for tool display."""
    return _load().get("facts", [])
