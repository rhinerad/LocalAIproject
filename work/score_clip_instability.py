"""Read-only triage for Equal Shares clips.

Samples every clip at 2 fps and measures the largest single frame-to-frame
luminance step against that clip's own median step. A continuous shot scores
low. A cut, a morph, or a sudden population change produces a spike.

This is a PRIORITISATION AID, NOT AN ACCEPTANCE TEST. Two known limits:

  * It misses slow morphs. A clip whose camera moves throughout spreads the
    transition across many frames and scores low despite having a real cut.
    Clip 12C scores 1.3 and is a confirmed reject. A low score is not a pass.
  * A high score is not a fault. Legitimate fast action scores high, and
    several human-approved clips sit at the top of the list.

Nothing here touches the GPU, ComfyUI, or port 8188, and nothing is written
into the shared output tree. Safe to run while the supervisor is rendering.

Usage:
    python work/score_clip_instability.py [--manifest outputs/equal_shares/manifest.json]
                                          [--story-root A:/Users/rhine/ComfyUI-Shared/output/story]
                                          [--json out.json]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

try:
    import numpy as np
    from PIL import Image
except ImportError:  # pragma: no cover
    sys.exit("requires numpy and pillow: pip install numpy pillow")

DEFAULT_STORY_ROOT = r"A:\Users\rhine\ComfyUI-Shared\output\story"
DEFAULT_MANIFEST = os.path.join("outputs", "equal_shares", "manifest.json")


def selected_source(manifest_path: str) -> dict[str, str]:
    """Map clip id -> the raw file the manifest actually selected.

    Picking the last file in a directory is wrong for any clip with multiple
    attempts, so always go through the manifest.
    """
    with open(manifest_path, encoding="utf-8-sig") as handle:
        clips = json.load(handle)["clips"]
    return {cid: rec.get("comfy_source") for cid, rec in clips.items() if rec.get("comfy_source")}


def score(path: str, fps: float = 2.0, width: int = 160, height: int = 90) -> dict | None:
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [
            "ffmpeg", "-v", "error", "-y", "-i", path,
            "-vf", f"fps={fps},scale={width}:{height}",
            os.path.join(tmp, "%04d.png"),
        ]
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
        names = sorted(os.listdir(tmp))
        if len(names) < 3:
            return None
        frames = [
            np.asarray(Image.open(os.path.join(tmp, n)).convert("L"), dtype=np.float32)
            for n in names
        ]

    steps = np.array([float(np.abs(frames[i + 1] - frames[i]).mean()) for i in range(len(frames) - 1)])
    median = float(np.median(steps))
    return {
        "frames_sampled": len(frames),
        "max_step": float(steps.max()),
        "median_step": median,
        "ratio": float(steps.max() / max(median, 0.5)),
        "drift_first_to_last": float(np.abs(frames[-1] - frames[0]).mean()),
        "peak_at_seconds": round((int(steps.argmax()) + 1) / fps, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--story-root", default=DEFAULT_STORY_ROOT)
    parser.add_argument("--json", default=None, help="also write results here")
    parser.add_argument("--only", nargs="*", help="limit to these clip ids")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        return f"manifest not found: {args.manifest}" and 2

    sources = selected_source(args.manifest)
    if args.only:
        sources = {k: v for k, v in sources.items() if k in set(args.only)}

    results = []
    for cid in sorted(sources):
        raw = sources[cid]
        # Manifest stores an absolute Windows path; fall back to story-root + filename.
        path = raw if os.path.exists(raw) else os.path.join(args.story_root, cid, os.path.basename(raw))
        if not os.path.exists(path):
            print(f"{cid:6} MISSING {raw}", file=sys.stderr)
            continue
        row = score(path)
        if row is None:
            print(f"{cid:6} UNREADABLE {path}", file=sys.stderr)
            continue
        row["clip"] = cid
        row["source"] = path
        results.append(row)

    results.sort(key=lambda r: -r["ratio"])
    print(f"{'clip':6}{'max':>9}{'median':>9}{'ratio':>8}{'drift':>8}{'peak@s':>9}")
    for r in results:
        print(
            f"{r['clip']:6}{r['max_step']:>9.2f}{r['median_step']:>9.2f}"
            f"{r['ratio']:>8.1f}{r['drift_first_to_last']:>8.1f}{r['peak_at_seconds']:>9}"
        )

    if args.json:
        with open(args.json, "w", encoding="utf-8") as handle:
            json.dump(results, handle, indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
