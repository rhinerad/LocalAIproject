import argparse
import json
import math
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
MANIFEST = PROJECT / "manifest.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("clip_id")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    record = manifest.get("clips", {}).get(args.clip_id)
    if not record:
        raise SystemExit(f"No manifest record for {args.clip_id}")
    source_value = record.get("comfy_source") or record.get("clip")
    source = Path(source_value) if source_value else None
    if source is None or not source.is_file():
        raise SystemExit(f"No video source for {args.clip_id}")
    duration = float(record.get("duration", 5.0))
    columns = 5
    rows = max(1, math.ceil(duration / columns))
    output = PROJECT / "validation_contacts" / f"{args.clip_id}_manual_every_second.jpg"
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg unavailable")
    subprocess.run(
        [
            ffmpeg, "-y", "-v", "error", "-i", str(source),
            "-vf", f"fps=1,scale=320:-1,tile={columns}x{rows}:padding=4:margin=4",
            "-frames:v", "1", str(output),
        ],
        check=True,
        timeout=180,
    )
    print(output)


if __name__ == "__main__":
    main()
