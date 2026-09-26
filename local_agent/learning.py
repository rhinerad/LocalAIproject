"""Privacy-preserving, bounded cross-chat improvement signals."""
from __future__ import annotations
import hashlib, json, time
from pathlib import Path

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
DIR = HERE / "runtime" / "learning"
LEDGER = DIR / "failure_ledger.jsonl"
REVIEW = DIR / "self_review.json"
ADVICE = {
    "context": "A long-chat context budget was exceeded before. Preserve the current request; continuity notes are secondary.",
    "model": "A selected model was unavailable before. Check live routing/model availability instead of relying on memory.",
    "tool": "A tool has failed repeatedly. Report its returned error exactly and never invent missing evidence.",
    "generation": "A prior generation ended with a backend error. Do not present a tool result as a completed answer.",
}

def _category(event: str, payload: str) -> str | None:
    text = str(payload or "")
    if "context compacted:" in text or "exceed this context" in text: return "context"
    if "No model available" in text or "selected model is pulled" in text: return "model"
    if event == "tool_result" and (text.startswith("ERROR") or text.startswith("REFUSED")): return "tool"
    if event == "error": return "generation"
    return None

def _load() -> dict:
    try: return json.loads(REVIEW.read_text(encoding="utf8"))
    except Exception: return {"counts": {}}

def record(event: str, payload: str, chat_id: str = "") -> None:
    category = _category(event, payload)
    if not category: return
    DIR.mkdir(parents=True, exist_ok=True)
    row = {"at": time.time(), "category": category, "event": event,
           "signature": hashlib.sha256(str(payload).encode("utf8", "replace")).hexdigest()[:16],
           "chat": str(chat_id)[:40]}
    with LEDGER.open("a", encoding="utf8") as f: f.write(json.dumps(row) + "\n")
    review = _load(); counts = review.setdefault("counts", {})
    counts[category] = int(counts.get(category, 0)) + 1; review["updated"] = row["at"]
    atomic_write_text(REVIEW, json.dumps(review, indent=2))

def prompt_block() -> str:
    return "\n".join(f"- {ADVICE[key]}" for key, count in _load().get("counts", {}).items()
                     if int(count) >= 2 and key in ADVICE)
