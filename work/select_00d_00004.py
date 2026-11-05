#!/usr/bin/env python3
"""Select user-approved 00D picture while permanently discarding H3 audio."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
SOURCE = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00D\attempt_1_00004_.mp4")
DESTINATION = PROJECT / "clips" / "001_00D.mp4"
OVERVIEW = PROJECT / "validation_contacts" / "00D_attempt_00004_every_second.jpg"
ENDING = PROJECT / "validation_contacts" / "00D_attempt_7_duration_rejected_ending.jpg"

ffmpeg = shutil.which("ffmpeg")
if not ffmpeg or not SOURCE.is_file():
    raise SystemExit("ffmpeg or approved source is unavailable")
DESTINATION.parent.mkdir(parents=True, exist_ok=True)
result = subprocess.run(
    [ffmpeg, "-y", "-v", "error", "-i", str(SOURCE), "-map", "0:v:0", "-c:v", "copy", "-an", str(DESTINATION)],
    capture_output=True,
    text=True,
)
if result.returncode:
    raise SystemExit(result.stderr)

manifest_path = PROJECT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest.setdefault("clips", {})["00D"] = {
    "status": "valid",
    "attempt_total": 7,
    "clip": str(DESTINATION),
    "comfy_source": str(SOURCE),
    "chunk_archive": str(SOURCE),
    "duration": 12.0,
    "frames": 294,
    "steps": 15,
    "used_last_frame": True,
    "first_frame": "frames/scene_000/boundary_entry_start_v2.png",
    "last_frame": "frames/scene_000/boundary_01_v2.png",
    "visual_validation": (
        "User confirmed attempt_1_00004 fixed the 00003 error. Every-second review shows exactly "
        "two male visitors, receptionist always behind desk, no narrator visible, and no one sits."
    ),
    "validation_contact": str(OVERVIEW),
    "validation_ending": str(ENDING),
    "raw_audio_discarded": True,
    "dialogue_source": "postproduction narrator track",
    "user_approved_visual": True,
    "rejected_predecessor": r"A:\Users\rhine\ComfyUI-Shared\output\story\00D\attempt_1_00003_.mp4",
}
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

review_path = PROJECT / "visual_review.json"
review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
review["00D"] = {
    "status": "approved_visual_only",
    "source": str(SOURCE),
    "notes": "00004 fixed the three-man error; generated gibberish removed completely and narration added in post.",
}
review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
print(DESTINATION)
