#!/usr/bin/env python3
"""Auditable, reversible quality accounting for approved exemplars.

It works on the local review files today and deliberately has no dependency on
Chroma. A future, operator-approved embedding adapter can use the same IDs.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from atomic_io import atomic_write_text
import exemplar_curator

HERE = Path(__file__).resolve().parent
ATTRIBUTIONS = HERE / "runtime" / "exemplar_lifecycle" / "attributions.json"
ARCHIVE = exemplar_curator.ROOT / "archive"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic(path: Path, value: object) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2))


def _read_attributions() -> dict:
    if not ATTRIBUTIONS.is_file():
        return {}
    try:
        value = json.loads(ATTRIBUTIONS.read_text(encoding="utf8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def record_attribution(message_id: str, retrieved_ids: list[str]) -> None:
    """Log only IDs, never prompt text or chat content."""
    clean = sorted({str(value) for value in retrieved_ids if str(value).startswith("stage_")})
    if not message_id or not clean:
        return
    rows = _read_attributions()
    rows[str(message_id)] = {"exemplar_ids": clean, "recorded_at": _now()}
    _atomic(ATTRIBUTIONS, rows)


def _approved_path(identifier: str) -> Path:
    return exemplar_curator.APPROVED / f"{Path(str(identifier)).name}.json"


def update_scores(message_id: str, rating: str) -> dict:
    if rating not in {"positive", "negative"}:
        raise ValueError("rating must be positive or negative")
    row = _read_attributions().get(str(message_id), {})
    changed = []
    for identifier in row.get("exemplar_ids", []):
        path = _approved_path(identifier)
        if not path.is_file():
            continue
        record = json.loads(path.read_text(encoding="utf8"))
        metrics = record.setdefault("lifecycle", {"positive_uses": 0, "negative_uses": 0})
        key = "positive_uses" if rating == "positive" else "negative_uses"
        metrics[key] = int(metrics.get(key, 0)) + 1
        total = int(metrics.get("positive_uses", 0)) + int(metrics.get("negative_uses", 0))
        score = int(metrics.get("positive_uses", 0)) / total if total else 0.0
        metrics["quality_score"] = score
        metrics["status"] = "needs_review" if total >= 5 and score < 0.40 else "active"
        _atomic(path, record)
        changed.append(identifier)
    return {"updated": changed, "rating": rating}


def audit_health(collection_name: str = "approved") -> dict:
    if collection_name != "approved":
        raise ValueError("only the local approved collection exists until an embedding backend is approved")
    items, review = 0, []
    for path in exemplar_curator.APPROVED.glob("*.json") if exemplar_curator.APPROVED.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf8"))
        items += 1
        metrics = record.get("lifecycle", {})
        total = int(metrics.get("positive_uses", 0)) + int(metrics.get("negative_uses", 0))
        score = int(metrics.get("positive_uses", 0)) / total if total else None
        if total >= 5 and score is not None and score < 0.40:
            review.append(record.get("id"))
    return {"collection": collection_name, "items": items, "needs_review": review}


def archive_stale_exemplars(collection_name: str = "approved", threshold: float = 0.40) -> dict:
    if collection_name != "approved":
        raise ValueError("only the local approved collection exists until an embedding backend is approved")
    archived = []
    for path in list(exemplar_curator.APPROVED.glob("*.json")) if exemplar_curator.APPROVED.is_dir() else []:
        record = json.loads(path.read_text(encoding="utf8"))
        metrics = record.get("lifecycle", {})
        pos, neg = int(metrics.get("positive_uses", 0)), int(metrics.get("negative_uses", 0))
        total = pos + neg
        if total >= 5 and pos / total < threshold:
            record["status"] = "archived"
            record["archived_at"] = _now()
            _atomic(ARCHIVE / path.name, record)
            path.unlink()  # reversible archive; the complete record is retained under archive.
            archived.append(record["id"])
    return {"archived": archived, "threshold": threshold}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prune-stale", action="store_true")
    args = parser.parse_args()
    print(json.dumps(archive_stale_exemplars() if args.prune_stale else audit_health(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
