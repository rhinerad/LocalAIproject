#!/usr/bin/env python3
"""Select validated 00D2 picture with its H3 audio removed."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
SOURCE = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00D2\attempt_1_00002_.mp4")
DESTINATION = PROJECT / "clips" / "001_00D2.mp4"
CONTACT = PROJECT / "validation_contacts" / "00D2_attempt_00002_every_second.jpg"
ENDING = PROJECT / "validation_contacts" / "00D2_attempt_2_ending.jpg"

manifest_path = PROJECT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest.setdefault("clips", {})["00D2"] = {
    "status": "valid",
    "attempt_total": 2,
    "clip": str(DESTINATION),
    "comfy_source": str(SOURCE),
    "chunk_archive": str(SOURCE),
    "duration": 10.0,
    "frames": 243,
    "steps": 15,
    "used_last_frame": True,
    "first_frame": "frames/scene_000/boundary_01_v2.png",
    "last_frame": "frames/scene_000/boundary_02_v2.png",
    "visual_validation": (
        "Every-second review: exactly two male visitors; Person One alone sits; Person Two remains "
        "standing; receptionist stays behind desk; narrator absent."
    ),
    "validation_contact": str(CONTACT),
    "validation_ending": str(ENDING),
    "raw_audio_discarded": True,
    "dialogue_source": "postproduction narrator track",
}
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

review_path = PROJECT / "visual_review.json"
review = json.loads(review_path.read_text(encoding="utf-8")) if review_path.exists() else {}
review["00D2"] = {
    "status": "approved_visual_only",
    "source": str(SOURCE),
    "notes": "Two men only; one seated/one standing; receptionist always behind desk; raw audio removed.",
}
review_path.write_text(json.dumps(review, indent=2, ensure_ascii=False), encoding="utf-8")
print("Selected", SOURCE)
