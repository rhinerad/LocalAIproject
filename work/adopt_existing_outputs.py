#!/usr/bin/env python3
"""Adopt valid ComfyUI source chunks after a detached runner or copy failure."""

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def duration(path: Path) -> float | None:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        return float(result.stdout.strip()) if result.returncode == 0 else None
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=Path)
    parser.add_argument("--only", action="append", dest="only_ids")
    args = parser.parse_args()

    config_path = args.config.resolve()
    project = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))
    clips = config["clips"]
    selected = set(args.only_ids or [clip["id"] for clip in clips])
    manifest_path = project / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"clips": {}}
    manifest.setdefault("clips", {})
    clips_dir = project / "clips"
    clips_dir.mkdir(exist_ok=True)
    source_root = Path(config["comfy_output_root"]) / "story"
    adopted = 0

    for sequence, clip in enumerate(clips, 1):
        clip_id = clip["id"]
        if clip_id not in selected:
            continue
        expected = float(clip["duration"])
        candidates = sorted((source_root / clip_id).glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        source = next((p for p in candidates if (d := duration(p)) is not None and abs(d - expected) <= float(config.get("duration_tolerance", 1))), None)
        if source is None:
            print(f"MISS {clip_id}: no valid existing output")
            continue
        measured = duration(source)
        destination = clips_dir / f"{sequence:03d}_{clip_id}{source.suffix.lower()}"
        shutil.copy2(source, destination)
        prior = manifest["clips"].get(clip_id, {})
        manifest["clips"][clip_id] = {
            "status": "valid",
            "attempt": prior.get("attempt"),
            "attempt_total": prior.get("attempt_total", prior.get("attempt", 0)),
            "seed": prior.get("seed"),
            "prompt_id": prior.get("prompt_id", "adopted-from-comfy-output"),
            "clip": str(destination),
            "comfy_source": str(source),
            "chunk_archive": str(source),
            "duration": expected,
            "frames": int(clip["frames"]),
            "first_frame": clip.get("first_frame"),
            "last_frame": clip.get("last_frame"),
            "validation": f"duration={measured:.3f}s expected={expected:.3f}s; adopted existing ComfyUI source",
        }
        adopted += 1
        print(f"ADOPT {clip_id}: {source.name} ({measured:.3f}s)")

    temp = manifest_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(manifest_path)
    print(f"Adopted {adopted} clip(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
