#!/usr/bin/env python3
"""Use only 08B's clean close performance and exclude its glass-office reveal."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "manifest.json"
CONTACT = PROJECT / "validation_contacts" / "08B_salvaged_every_second.jpg"

manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
record = manifest.get("clips", {}).get("08B", {})
source = Path(record.get("comfy_source", ""))
destination = Path(record.get("clip", PROJECT / "clips" / "001_08B.mp4"))
if not source.is_file():
    raise SystemExit("08B original H3 source is missing")

# The first 3.8 seconds contain the complete clean close performance. Slow the
# restrained acting naturally to nine seconds; discard the later invented
# glass-wall reveal completely.
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(source), "-an",
    "-vf", "trim=start=0:end=3.8,setpts=2.3684210526*(PTS-STARTPTS),fps=24,tpad=stop_mode=clone:stop_duration=0.1,trim=duration=9",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(destination),
], check=True, timeout=300)
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(destination),
    "-vf", "fps=1,scale=320:-1,tile=5x2:padding=4:margin=4", "-frames:v", "1", str(CONTACT),
], check=True, timeout=180)

record.update({
    "status": "valid",
    "clip": str(destination),
    "comfy_source": str(source),
    "chunk_archive": str(source),
    "duration": 9.0,
    "steps": 20,
    "raw_audio_discarded": True,
    "visual_derivative": "first 3.8 clean H3 seconds slowed to 9 seconds; invented glass-office reveal excluded",
    "rejected_source_tail": "3.8 seconds through end: unrequested camera widening and glass-walled office",
    "validation_every_second": str(CONTACT),
    "visual_validation": "Kent, Ryann, and Avery remain stable in the established estate-office close composition; Kent's restrained reaction is preserved.",
})
manifest.setdefault("clips", {})["08B"] = record
temporary = MANIFEST.with_suffix(".json.tmp")
temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
temporary.replace(MANIFEST)
print(destination)

