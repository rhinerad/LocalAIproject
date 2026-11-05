#!/usr/bin/env python3
"""Promote or reject a reviewed Stage-1 MiniMax H3 soundtrack candidate.

Promotion copies the exact candidate WAV to the accepted collection and records
source provenance. Nothing is moved, deleted, or overwritten.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "audio_pass_manifest.json"
ACCEPTED = PROJECT / "audio" / "h3_dialogue"


def save(data: dict) -> None:
    temp = MANIFEST.with_name(f"{MANIFEST.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, MANIFEST)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--accept", action="store_true")
    action.add_argument("--reject", action="store_true")
    parser.add_argument("--note", required=True)
    parser.add_argument("--reviewer", default="local-agent")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        raise SystemExit(f"manifest not found: {MANIFEST}")
    data = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    entry = data.get("clips", {}).get(args.clip)
    if not entry or not entry.get("attempts"):
        raise SystemExit(f"no audio attempt recorded for {args.clip}")
    attempt = entry["attempts"][-1]
    stamp = datetime.now().isoformat(timespec="seconds")

    review = {
        "verdict": "accepted" if args.accept else "rejected",
        "reviewed_at": stamp,
        "reviewer": args.reviewer,
        "note": args.note,
        "attempt": attempt.get("attempt"),
        "validation_status": attempt.get("status"),
    }
    attempt.setdefault("reviews", []).append(review)

    if args.reject:
        entry["status"] = "review_rejected"
        entry["updated_at"] = stamp
        save(data)
        print(f"{args.clip}: rejected; source preserved")
        return 0

    if attempt.get("status") in {"render_error", "render_failed", "retry_required"}:
        raise SystemExit(
            f"cannot accept attempt in {attempt.get('status')} state; render/validate a new take"
        )
    candidate = Path(attempt.get("candidate_full_wav", ""))
    source_video = Path(attempt.get("source_video", ""))
    if not candidate.is_file() or not source_video.is_file():
        raise SystemExit("candidate WAV or source MiniMax MP4 is missing")

    ACCEPTED.mkdir(parents=True, exist_ok=True)
    attempt_no = int(attempt.get("attempt") or 0)
    destination = ACCEPTED / f"{args.clip}_a{attempt_no:02d}_full.wav"
    if destination.exists():
        if destination.stat().st_size != candidate.stat().st_size:
            raise SystemExit(f"accepted destination exists with different content: {destination}")
    else:
        shutil.copy2(candidate, destination)

    entry.update({
        "status": "accepted",
        "accepted_attempt": attempt_no,
        "accepted_full_wav": str(destination),
        "source_video": str(source_video),
        "validation_report": attempt.get("validation_report"),
        "accepted_at": stamp,
        "reviewer": args.reviewer,
        "review_note": args.note,
    })
    save(data)
    print(f"{args.clip}: accepted native MiniMax H3 soundtrack -> {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
