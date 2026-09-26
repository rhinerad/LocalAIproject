"""Small local-only lexical retrieval across prior desktop chats.

This is continuity assistance, not evidence: callers must still inspect files
and run tools for current state. It returns compact excerpts and never sends a
chat archive outside this workstation.
"""
from __future__ import annotations
import math, re
from pathlib import Path
import store

_TOK = re.compile(r"[a-z0-9]{3,}", re.I)
MAX_RESULTS, MAX_EXCERPT = 3, 1200
_GENERIC = {
    "about", "also", "and", "are", "can", "could", "did", "does", "doing",
    "fast", "for", "from", "have", "how", "i'm", "into", "just", "like",
    "make", "need", "please", "should", "test", "that", "the", "then", "these",
    "this", "things", "trying", "use", "want", "what", "with", "would", "you",
    "your",
}
_EQUAL_SHARES = re.compile(
    r"(?i)(?:\bequal\s+shares\b|\bminimax\s*h3\b|"
    r"outputs[\\/]equal_shares|\bduration\s+ladder\b|\bnative\s+r2v\b|"
    r"\bvoice[- ]lock\b|\bsoundtrack\s+pass\b)"
)

def _terms(text: str) -> set[str]:
    return set(t.lower() for t in _TOK.findall(text))


def _meaningful_terms(text: str) -> set[str]:
    """Return retrieval terms that can identify a topic, not chat filler."""
    return {term for term in _terms(text) if term not in _GENERIC}

def search(query: str, *, exclude_id: str = "", limit: int = MAX_RESULTS,
           include_project: bool = True) -> list[dict]:
    terms = _meaningful_terms(query)
    # Cross-chat recall is optional convenience, not a substitute for the
    # active transcript. Generic requests such as "test how fast you can do
    # things" must never select an unrelated old chat on pronouns or helpers.
    if len(terms) < 2:
        return []
    scored=[]
    for item in store.listing():
        if item["id"] == exclude_id:
            continue
        chat=store.load(item["id"])
        if not chat:
            continue
        # Only prior *operator* messages may be injected. Old assistant text
        # can contain a hallucination, a stale plan, or a tool result; treating
        # it as context for a new request is exactly how unrelated answers can
        # self-propagate across chats.
        msgs=chat.get("messages", [])[-12:]
        operator_messages = [str(m.get("content", "")) for m in msgs
                             if m.get("role") == "user"]
        text = "Operator's earlier topic: " + str(item.get("title", ""))
        if operator_messages:
            text += "\n" + "\n".join("Operator: " + value for value in operator_messages)
        # Prior chats are convenience-only continuity notes. A general request
        # must never receive an Equal Shares conversation merely because both
        # happen to contain broad words such as "project", "prompt", or
        # "render". Explicit project turns may search the whole archive.
        if not include_project and _EQUAL_SHARES.search(text):
            continue
        words=_meaningful_terms(text)
        overlap=len(terms & words)
        # Two specific terms are required. This intentionally declines vague
        # "continue"/"test" style queries rather than guessing a prior task.
        if overlap < 2:
            continue
        score=overlap / math.sqrt(max(len(words),1))
        scored.append((score, {"id":item["id"],"title":item["title"],"text":text[-MAX_EXCERPT:]}))
    return [x[1] for x in sorted(scored,key=lambda x:-x[0])[:limit] if x[0] >= .12]
