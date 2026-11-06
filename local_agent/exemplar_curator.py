#!/usr/bin/env python3
"""Local, explicit approval queue for external creative exemplars.

Candidates remain files under ``exemplar_staging/pending`` until the operator
reviews them.  This is deliberately separate from retrieval and model memory.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import atomic_write_text
import exemplar_filter

HERE = Path(__file__).resolve().parent
ROOT = HERE / "exemplar_staging"
PENDING, APPROVED, REJECTED = (ROOT / name for name in ("pending", "approved", "rejected"))
SOURCES = {"VidProM", "ComfyUI-Workflows", "WritingPrompts", "Manual"}
LICENSES = {"CC-BY-4.0", "MIT", "CC-BY-NC-4.0", "Public_Domain", "Internal"}
_CATEGORIES = {"video_prompt", "comfyui_workflow", "screenplay_beat"}
_DOMAINS = {"cinematic_live_action", "sci_fi", "h3_r2v", "general"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic(path: Path, value: dict) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def _all_records() -> list[dict]:
    rows = []
    for folder in (PENDING, APPROVED, REJECTED):
        if folder.is_dir():
            for path in folder.glob("*.json"):
                try:
                    rows.append(json.loads(path.read_text(encoding="utf8")))
                except (OSError, json.JSONDecodeError):
                    continue
    return rows


def stage(item: dict) -> dict:
    """Validate and add a candidate to pending; never activates/embeds it."""
    candidate = dict(item or {})
    for key, allowed in (("source_dataset", SOURCES), ("license", LICENSES),
                         ("category", _CATEGORIES), ("style_domain", _DOMAINS)):
        if candidate.get(key) not in allowed:
            raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    candidate["title"] = " ".join(str(candidate.get("title", "")).split())[:180]
    candidate["content"] = str(candidate.get("content", "")).strip()
    existing = {str(row.get("content_fingerprint", "")) for row in _all_records()}
    report = exemplar_filter.check_candidate(candidate, existing)
    if not report["ok"]:
        raise ValueError("; ".join(report["errors"]))
    identifier = "stage_%s_%s" % (candidate["category"], report["fingerprint"][:16])
    record = {
        "id": identifier, "source_dataset": candidate["source_dataset"],
        "license": candidate["license"], "category": candidate["category"],
        "style_domain": candidate["style_domain"], "title": candidate["title"],
        "content": candidate["content"], "metadata": dict(candidate.get("metadata") or {}),
        "status": "pending", "created_at": _now(), "content_fingerprint": report["fingerprint"],
        "pre_screen": report, "embedding": {"status": "not_requested"},
    }
    record["metadata"].setdefault("tags", [])
    _atomic(PENDING / f"{identifier}.json", record)
    return record


def pending() -> list[dict]:
    if not PENDING.is_dir():
        return []
    rows = []
    for path in sorted(PENDING.glob("*.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf8")))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def review(identifier: str, action: str, *, content: str | None = None) -> dict:
    """Approve/edit/reject one staged item; only approval can enter local search."""
    if action not in {"approve", "edit_approve", "reject"}:
        raise ValueError("action must be approve, edit_approve, or reject")
    source = PENDING / f"{Path(str(identifier)).name}.json"
    if not source.is_file():
        raise ValueError("pending staged item not found")
    record = json.loads(source.read_text(encoding="utf8"))
    if action == "edit_approve":
        if not isinstance(content, str) or not content.strip():
            raise ValueError("edit_approve needs replacement content")
        record["content"] = content.strip()
        recheck = exemplar_filter.check_candidate(record)
        if not recheck["ok"]:
            raise ValueError("; ".join(recheck["errors"]))
        record["content_fingerprint"] = recheck["fingerprint"]
        record["pre_screen"] = recheck
    record["status"] = "rejected" if action == "reject" else "approved"
    record["reviewed_at"] = _now()
    if action == "reject":
        record["embedding"] = {"status": "not_requested", "note": "Rejected items never enter retrieval."}
    else:
        try:
            import exemplar_embeddings
            record["embedding"] = exemplar_embeddings.embed_record(record)
        except Exception as exc:
            # Approval is retained. The background worker can retry this record
            # later, but a failed embedding is never silently searchable.
            record["embedding"] = {"status": "deferred", "reason": f"{type(exc).__name__}: {exc}"}
    destination = REJECTED if action == "reject" else APPROVED
    _atomic(destination / source.name, record)
    source.unlink()
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Review locally staged exemplar candidates")
    parser.add_argument("--interactive", action="store_true")
    args = parser.parse_args()
    rows = pending()
    if not args.interactive:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print("No pending exemplar candidates.")
        return 0
    for row in rows:
        print(f"\n{row['id']} | {row['category']} | {row['license']}\n{row['title']}\n{row['content'][:500]}")
        choice = input("[a]pprove, [r]eject, [s]kip: ").strip().lower()
        if choice == "a": review(row["id"], "approve")
        elif choice == "r": review(row["id"], "reject")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
