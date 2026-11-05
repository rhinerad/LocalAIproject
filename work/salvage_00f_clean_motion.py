#!/usr/bin/env python3
"""Use only the clean two-man portion of 00F and discard its later drift."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
SOURCE = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\00F\attempt_1_00002_.mp4")
DESTINATION = PROJECT / "clips" / "001_00F.mp4"
CONTACT = PROJECT / "validation_contacts" / "00F_salvaged_every_second.jpg"

subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(SOURCE),
    "-an", "-vf", "trim=duration=6,setpts=2.5*(PTS-STARTPTS),fps=24,tpad=stop_mode=clone:stop_duration=0.2,trim=duration=15",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(DESTINATION),
], check=True)
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(DESTINATION),
    "-vf", "fps=1,scale=320:-1,tile=5x3:padding=4:margin=4", "-frames:v", "1", str(CONTACT),
], check=True)

manifest_path = PROJECT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
record = manifest.setdefault("clips", {}).setdefault("00F", {})
record.update({
    "status": "valid",
    "clip": str(DESTINATION),
    "comfy_source": str(SOURCE),
    "chunk_archive": str(SOURCE),
    "duration": 15.0,
    "raw_audio_discarded": True,
    "visual_derivative": "first 6 clean seconds slowed to 15 seconds; later drift excluded",
    "rejected_source_tail": "6.0s through end: reception reveal and invented doorway people",
    "validation_every_second": str(CONTACT),
    "visual_validation": "Exactly two male visitors throughout; Person One seated and Person Two standing; receptionist/narrator remain offscreen.",
})
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
print(DESTINATION)
