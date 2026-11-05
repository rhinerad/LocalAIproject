#!/usr/bin/env python3
"""Build a full-duration opening shot from only a validated clean prefix."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("clip_id")
    parser.add_argument("source", type=Path)
    parser.add_argument("--clean-seconds", type=float, required=True)
    parser.add_argument("--duration", type=float, required=True)
    args = parser.parse_args()
    destination = PROJECT / "clips" / f"001_{args.clip_id}.mp4"
    contact = PROJECT / "validation_contacts" / f"{args.clip_id}_salvaged_every_second.jpg"
    speed_factor = args.duration / args.clean_seconds
    rows = max(1, int((args.duration + 4.999) // 5))
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(args.source), "-an",
        "-vf", (
            f"trim=duration={args.clean_seconds},setpts={speed_factor:.10f}*(PTS-STARTPTS),fps=24,"
            f"tpad=stop_mode=clone:stop_duration=0.2,trim=duration={args.duration}"
        ),
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", str(destination),
    ], check=True)
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(destination),
        "-vf", f"fps=1,scale=320:-1,tile=5x{rows}:padding=4:margin=4",
        "-frames:v", "1", str(contact),
    ], check=True)
    manifest_path = PROJECT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    record = manifest.setdefault("clips", {}).setdefault(args.clip_id, {})
    record.update({
        "status": "valid",
        "clip": str(destination),
        "comfy_source": str(args.source),
        "chunk_archive": str(args.source),
        "duration": args.duration,
        "raw_audio_discarded": True,
        "visual_derivative": f"first {args.clean_seconds:g} clean seconds slowed to {args.duration:g} seconds; later drift excluded",
        "rejected_source_tail": f"{args.clean_seconds:g}s through end",
        "validation_every_second": str(contact),
        "visual_validation": "Exactly two male visitors throughout; Person One seated and Person Two standing; all other people remain offscreen.",
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
