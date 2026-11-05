"""Extract the final frame of a rendered clip and save it as a PNG.

This is the automation equivalent of the node chain added to the manual ComfyUI
workflow (GetVideoComponents -> GetImageSize -> ComfyMathExpression -> ImageFromBatch
-> SaveImage), which pulls the last frame out of each generated video so it can
become the opening anchor of the next shot.

Doing it with ffmpeg instead of in the graph keeps the proven H3 workflow
untouched, and works retroactively on clips that were rendered before the idea
existed.

Read-only with respect to the archive: it never modifies or deletes a video, and
writes only new PNGs.

Usage (from the folder containing outputs\\ and work\\):
    python work\\save_last_frames.py                  # every clip in the manifest
    python work\\save_last_frames.py --only 00E 00F
    python work\\save_last_frames.py --out outputs\\equal_shares\\frames\\derived
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

MANIFEST = os.path.join("outputs", "equal_shares", "manifest.json")
DEFAULT_OUT = os.path.join("outputs", "equal_shares", "frames", "derived_last_frames")
STORY_ROOT = r"A:\Users\rhine\ComfyUI-Shared\output\story"


def basename(path: str) -> str:
    """Manifest paths are Windows-style. Split on both separators so this also
    works when the script is run from a non-Windows host."""
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def selected_sources(manifest_path):
    with open(manifest_path, encoding="utf-8-sig") as fh:
        clips = json.load(fh)["clips"]
    return {cid: rec.get("comfy_source") for cid, rec in clips.items() if rec.get("comfy_source")}


def last_frame(video: str, out_png: str) -> bool:
    """Seek to the end and take the final decodable frame."""
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True)
    try:
        dur = float(probe.stdout.strip())
    except ValueError:
        return False
    # -sseof is the reliable way to land on the true last frame
    r = subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-sseof", "-0.2", "-i", video,
         "-update", "1", "-frames:v", "1", out_png],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_png):
        # fallback: seek to just before the end
        r = subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-ss", f"{max(dur - 0.05, 0):.3f}", "-i", video,
             "-frames:v", "1", out_png], capture_output=True, text=True)
    return os.path.exists(out_png)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--story-root", default=STORY_ROOT)
    args = ap.parse_args()

    if not os.path.exists(args.manifest):
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        return 2

    src = selected_sources(args.manifest)
    if args.only:
        src = {k: v for k, v in src.items() if k in set(args.only)}
    os.makedirs(args.out, exist_ok=True)

    ok = fail = 0
    for cid in sorted(src):
        raw = src[cid]
        path = raw if os.path.exists(raw) else os.path.join(args.story_root, cid, basename(raw))
        if not os.path.exists(path):
            print(f"{cid:6} MISSING  {raw}", file=sys.stderr)
            fail += 1
            continue
        out = os.path.join(args.out, f"{cid}_last_frame.png")
        if last_frame(path, out):
            print(f"{cid:6} -> {out}")
            ok += 1
        else:
            print(f"{cid:6} FAILED   {path}", file=sys.stderr)
            fail += 1

    print(f"\nwrote {ok} frame(s), {fail} failure(s), into {args.out}")
    print("These are derived images, not approved references. Inspect one before using it")
    print("as an anchor, and never overwrite a file in frames\\scene_### with one of these.")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
