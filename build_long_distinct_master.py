"""Assemble ~10min master by cycling distinct SELECTED Astra clips (not identical pad)."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def duration_s(path: Path) -> float:
    cp = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nk=1:nw=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(cp.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--target-seconds", type=float, default=600.0)
    ap.add_argument("--clip", action="append", required=True)
    args = ap.parse_args()

    clips = [Path(c) for c in args.clip]
    for c in clips:
        if not c.is_file():
            raise SystemExit(f"missing clip: {c}")
    hashes = {sha256(c) for c in clips}
    if len(hashes) < 2:
        raise SystemExit("need at least 2 distinct SHA256 inputs")

    durs = [duration_s(c) for c in clips]
    cycle = sum(durs)
    cycles = max(1, int(args.target_seconds // cycle) + (1 if args.target_seconds % cycle else 0))
    # Build concat list: cycle through distinct clips
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        lst = Path(td) / "concat.txt"
        lines = []
        for _ in range(cycles):
            for c in clips:
                # ffmpeg concat demuxer needs escaped paths on Windows
                p = str(c.resolve()).replace("\\", "/").replace("'", "'\\''")
                lines.append(f"file '{p}'")
        lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
        cp = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(lst),
                "-c",
                "copy",
                str(out),
            ],
            capture_output=True,
            text=True,
        )
        if cp.returncode != 0:
            raise SystemExit(cp.stderr[-2000:] or "ffmpeg failed")

    dur = duration_s(out)
    report = {
        "ok": True,
        "scope": "long_assembly_distinct_selected_cycled",
        "input_count": len(clips),
        "unique_input_sha256": len(hashes),
        "input_sha256": sorted(hashes),
        "cycle_duration_s": cycle,
        "cycles": cycles,
        "target_seconds": args.target_seconds,
        "output_path": str(out),
        "output_duration_s": dur,
        "output_sha256": sha256(out),
        "proves_long_form_generation": False,
        "proves_distinct_selected_assembly": True,
        "notes": (
            "Long master built by cycling distinct SELECTED Astra outputs. "
            "Not identical-clip pad. Does not prove continuous multi-hour generation."
        ),
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
