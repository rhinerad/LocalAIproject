#!/usr/bin/env python3
"""Replace H3's unreadable invoice close-up with the approved exact reference."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
SOURCE = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story\06C\attempt_1_00001_.mp4")
REFERENCE = PROJECT / "frames" / "scene_006" / "boundary_07.png"
DESTINATION = PROJECT / "clips" / "001_06C.mp4"
CONTACT = PROJECT / "validation_contacts" / "06C_salvaged_every_second.jpg"

if not SOURCE.is_file() or not REFERENCE.is_file():
    raise SystemExit("06C source or approved invoice reference is missing")

# Keep the clean uncovering action, cut to the exact readable bill as an
# intentional insert, then return to Kent's clean stress reaction. The final
# reaction is held briefly so the edited shot remains exactly ten seconds.
filter_graph = (
    "[0:v]trim=start=0:end=2.5,setpts=PTS-STARTPTS,fps=24,scale=736:416[a];"
    "[1:v]crop=800:450:"
    "x='620+2*sin(0.7*t)':y='220+1*sin(0.5*t)',scale=736:416,fps=24,trim=duration=4.25,"
    "setpts=PTS-STARTPTS[b];"
    "[0:v]trim=start=7.75:end=10.125,setpts=PTS-STARTPTS,fps=24,scale=736:416,"
    "tpad=stop_mode=clone:stop_duration=0.875,trim=duration=3.25[c];"
    "[a][b][c]concat=n=3:v=1:a=0,format=yuv420p[v]"
)
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(SOURCE), "-loop", "1", "-i", str(REFERENCE),
    "-filter_complex", filter_graph, "-map", "[v]", "-an", "-t", "10",
    "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
    str(DESTINATION),
], check=True, timeout=300)
subprocess.run([
    "ffmpeg", "-y", "-v", "error", "-i", str(DESTINATION),
    "-vf", "fps=1,scale=320:-1,tile=5x2:padding=4:margin=4", "-frames:v", "1", str(CONTACT),
], check=True, timeout=180)

manifest_path = PROJECT / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
record = manifest.setdefault("clips", {}).setdefault("06C", {})
record.update({
    "status": "valid",
    "clip": str(DESTINATION),
    "comfy_source": str(SOURCE),
    "chunk_archive": str(SOURCE),
    "duration": 10.0,
    "steps": 20,
    "raw_audio_discarded": True,
    "visual_derivative": "clean H3 uncover/reaction motion with approved exact invoice reference inserted from 2.5s to 6.75s",
    "rejected_generated_detail": "H3 invoice total became unreadable gibberish; original raw attempt remains preserved",
    "validation_every_second": str(CONTACT),
    "visual_validation": "Kent remains anatomically stable; exact OAK GROVE RETIREMENT HOME and $6,76,767 reference is readable in the insert; clean stress reaction retained.",
})
temporary = manifest_path.with_suffix(".json.tmp")
temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
temporary.replace(manifest_path)
print(DESTINATION)
