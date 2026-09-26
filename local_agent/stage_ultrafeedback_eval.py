#!/usr/bin/env python3
"""Stage a bounded UltraFeedback preference sample for *human-reviewed evals*.

This intentionally is not a Chroma ingestion tool. Preference pairs can improve
the local agent only after a reviewer converts a useful pair into a concrete,
anonymised acceptance test in ``operator_eval.py``. Injecting generic answers
into live retrieval would make tool use less grounded, not more reliable.

The default command is a no-network plan. ``--execute`` is the explicit network
download gate. It streams from Hugging Face, uses deterministic reservoir
sampling, and writes only pending records with source/license provenance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

HERE = Path(__file__).resolve().parent
ROOT = HERE / "dataset_eval_staging"
PENDING = ROOT / "pending"
DATASET_ID = "HuggingFaceH4/ultrafeedback_binarized"
SPLIT = "train_prefs"
LICENSE = "MIT"
MAX_TEXT_CHARS = 12_000
_SPACE = re.compile(r"\s+")


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean(value: object) -> str:
    """Normalize either a plain string or a chat-message list without guessing fields."""
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                content = item.get("content")
                if content:
                    parts.append(str(content))
            elif item:
                parts.append(str(item))
        value = "\n".join(parts)
    return _SPACE.sub(" ", str(value or "")).strip()[:MAX_TEXT_CHARS]


def _fields(row: dict) -> tuple[str, str, str] | None:
    """Use documented preference concepts while safely tolerating field wrappers."""
    prompt = _clean(row.get("prompt") or row.get("instruction") or row.get("messages"))
    chosen = _clean(row.get("chosen"))
    rejected = _clean(row.get("rejected"))
    if not prompt or not chosen or not rejected:
        return None
    # Evaluation records should be legible and bounded; they are not training rows.
    if min(len(prompt), len(chosen), len(rejected)) < 24:
        return None
    return prompt, chosen, rejected


def reservoir(rows: Iterable[dict], count: int, seed: int) -> list[dict]:
    """Return a deterministic uniform sample without downloading the full corpus."""
    rng = random.Random(seed)
    sample: list[dict] = []
    for index, row in enumerate(rows, start=1):
        if len(sample) < count:
            sample.append(row)
            continue
        target = rng.randrange(index)
        if target < count:
            sample[target] = row
    return sample


def records(rows: Iterable[dict], *, count: int, seed: int) -> Iterator[dict]:
    for fields in (_fields(row) for row in reservoir(rows, count, seed)):
        if fields is None:
            continue
        prompt, chosen, rejected = fields
        digest = hashlib.sha256((prompt + "\n" + chosen + "\n" + rejected).encode("utf-8")).hexdigest()[:16]
        yield {
            "id": f"dataset_eval_ultrafeedback_{digest}",
            "created_at": _now(),
            "status": "pending_review",
            "source_dataset": DATASET_ID,
            "dataset_split": SPLIT,
            "license": LICENSE,
            "intended_use": "offline_evaluation_candidate_only",
            "prompt": prompt,
            "preferred_response": chosen,
            "rejected_response": rejected,
            "review_requirements": [
                "Verify licensing/provenance remains acceptable for the intended use.",
                "Remove any private, unsafe, or irrelevant content.",
                "Convert to a concrete anonymised operator_eval case before scoring.",
                "Do not add this record to live retrieval or Chroma directly.",
            ],
        }


def write_pending(items: Iterable[dict], directory: Path = PENDING) -> int:
    directory.mkdir(parents=True, exist_ok=True)
    written = 0
    for record in items:
        path = directory / f"{record['id']}.json"
        if path.exists():
            continue
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written += 1
    return written


def stream_dataset() -> Iterable[dict]:
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError("Hugging Face datasets is not installed; install it only with operator approval.") from exc
    return load_dataset(DATASET_ID, split=SPLIT, streaming=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage UltraFeedback preference pairs for human-reviewed evals.")
    parser.add_argument("--execute", action="store_true", help="explicitly allow the network stream and local staging write")
    parser.add_argument("--count", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=20260826)
    args = parser.parse_args()
    if not 1 <= args.count <= 2000:
        parser.error("--count must be between 1 and 2000")
    plan = {"dataset": DATASET_ID, "split": SPLIT, "count": args.count,
            "seed": args.seed, "destination": str(PENDING),
            "mode": "offline evaluation staging only; no Chroma ingestion"}
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    try:
        staged = write_pending(records(stream_dataset(), count=args.count, seed=args.seed))
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({**plan, "staged": staged}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
