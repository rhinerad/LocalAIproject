"""Render one Equal Shares clip at several resolutions and compare the results.

WHY THIS EXISTS
---------------
The reference frames in this project are all 1672x941 (1.57 MP). Generation
runs at 736x416 (0.31 MP), so every anchor is downscaled to under a fifth of
its pixels before the model sees it. The MiniMax H3 prompting guide gives the
model's native output as 2K with a 1440 px short edge. Face and identity
failure has been the dominant rejection reason in review.

This script tests whether output resolution is the cause, by rendering the
same clip -- same seed, same prompt, same anchors, same 20 steps -- at several
sizes and putting the faces side by side at native scale.

HOW RESOLUTION IS ACTUALLY SET
------------------------------
Not by width/height. The proven H3 graph contains a ResolutionSelector node,
and minimax_story_runner.py drives it with config["megapixels"] plus the
aspect ratio and the multiple-of-32 rule. The {{WIDTH}}/{{HEIGHT}} tokens are
only used when no selector exists. So this script sweeps MEGAPIXELS, and then
measures what the selector actually produced with ffprobe rather than assuming.

SAFETY
------
  * Refuses to run while the render supervisor owns the queue.
  * Requires a ComfyUI backend already listening on 8188 -- it never starts or
    stops one, so it cannot collide with the supervisor's lifecycle.
  * Writes to a throwaway clip id, so raws land in
    ComfyUI-Shared/output/story/SWEEP_<clip>_<tag>/ and the real archive is
    never touched.
  * Writes its manifest into outputs/equal_shares/sweep_runs/, never the real
    manifest.json.
  * Reads story_config.json; never modifies it.

USAGE (from the folder containing outputs/ and work/)
-----------------------------------------------------
    $Py = "A:\\Users\\rhine\\ComfyUI-Installs\\Rockernow\\ComfyUI\\.venv\\Scripts\\python.exe"

    # start ComfyUI yourself first, then:
    & $Py work\\resolution_sweep.py 17C
    & $Py work\\resolution_sweep.py 17C --mp 0.31 0.59 1.43
    & $Py work\\resolution_sweep.py 18A --compare-only

Good candidates are clips rejected purely for face failure -- 17C and 18A --
because any improvement is unambiguous.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EQ = ROOT / "outputs" / "equal_shares"
CONFIG = EQ / "story_config.json"
RUNNER = ROOT / "outputs" / "minimax_story_runner.py"
OWNER = EQ / "runtime" / "render_queue_owner.json"
SWEEP = EQ / "sweep_runs"
SHARED_STORY = Path(r"A:\Users\rhine\ComfyUI-Shared\output\story")

# 16:9-ish targets whose dimensions are multiples of 32.
#   0.31 -> 736x416   (current)
#   0.59 -> 1024x576  (exactly 16:9)
#   1.43 -> 1600x896
#   1.54 -> 1664x928  (about the native size of the reference frames)
DEFAULT_MP = [0.31, 0.59, 1.43, 1.54]


def tag(mp: float) -> str:
    return f"{mp:.2f}".replace(".", "p") + "MP"


def port_open(host="127.0.0.1", port=8188, timeout=2.0) -> bool:
    with socket.socket() as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def pid_alive(pid: int) -> bool:
    if sys.platform.startswith("win"):
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"],
                             capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def preflight() -> None:
    if OWNER.exists():
        try:
            owner = json.loads(OWNER.read_text(encoding="utf-8"))
        except Exception:
            owner = {}
        pid = owner.get("pid")
        if pid and pid_alive(int(pid)):
            sys.exit(
                f"REFUSING TO RUN.\n"
                f"  {OWNER.name} says PID {pid} owns the render queue and that process is alive.\n"
                f"  Stop the supervisor (work/render_until_complete.py) first, at a clip boundary.\n"
                f"  Two processes must never share port 8188 or the GPU."
            )
        print(f"note: {OWNER.name} exists but PID {pid} is not running - treating the queue as free")
    if not port_open():
        sys.exit(
            "No ComfyUI backend is listening on 127.0.0.1:8188.\n"
            "  Start ComfyUI yourself, then re-run. This script deliberately never\n"
            "  starts or stops a backend, so it cannot fight the supervisor."
        )
    print("preflight ok: no live queue owner, backend is up on 8188")


def build_config(clip_id: str, mp: float) -> tuple[Path, str]:
    """Temp config in the same folder as story_config.json so relative frame
    paths still resolve, but with project_dir pointed at sweep_runs so the
    real manifest is untouched."""
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    clip = next((c for c in cfg["clips"] if c["id"] == clip_id), None)
    if clip is None:
        sys.exit(f"clip {clip_id} not found in story_config.json")

    sweep_id = f"SWEEP_{clip_id}_{tag(mp)}"
    clip = copy.deepcopy(clip)
    clip["id"] = sweep_id
    cfg["clips"] = [clip]
    cfg["megapixels"] = float(mp)
    cfg["project_dir"] = "sweep_runs"
    cfg["retries"] = 0

    SWEEP.mkdir(parents=True, exist_ok=True)
    path = EQ / f"_sweep_{clip_id}_{tag(mp)}.json"
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return path, sweep_id


def render(cfg_path: Path, sweep_id: str) -> Path | None:
    print(f"\n=== rendering {sweep_id} ===", flush=True)
    proc = subprocess.run([sys.executable, str(RUNNER), str(cfg_path), "--resume"],
                          cwd=str(ROOT))
    if proc.returncode != 0:
        print(f"  FAILED (exit {proc.returncode}) - continuing to the next size", file=sys.stderr)
        return None
    outdir = SHARED_STORY / sweep_id
    vids = sorted(outdir.glob("*.mp4")) if outdir.exists() else []
    if not vids:
        print(f"  no output found in {outdir}", file=sys.stderr)
        return None
    return vids[-1]


def probe(path: Path) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True).stdout.split()
    return int(out[0]), int(out[1]), float(out[2])


def compare(clip_id: str, results: list[dict], at: float, crop: str) -> None:
    """Full-frame strip plus a face-region strip, both at native pixel scale."""
    if not results:
        print("nothing to compare")
        return
    outdir = SWEEP / f"compare_{clip_id}"
    outdir.mkdir(parents=True, exist_ok=True)
    cx, cy, cw, ch = (float(v) for v in crop.split(","))
    tallest = max(r["h"] for r in results)

    fulls, faces = [], []
    for r in results:
        stem = outdir / f"{clip_id}_{r['tag']}"
        full = stem.with_name(stem.name + "_full.png")
        face = stem.with_name(stem.name + "_face.png")
        # Full frame, upscaled to a common height with nearest neighbour so the
        # real pixel density of each render stays visible.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(r["path"]),
                        "-frames:v", "1", "-vf", f"scale=-1:{tallest}:flags=neighbor",
                        str(full)], check=True)
        # Face region at native pixels, then 3x lanczos so it is inspectable.
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(at), "-i", str(r["path"]),
                        "-frames:v", "1",
                        "-vf", (f"crop=iw*{cw}:ih*{ch}:iw*{cx}:ih*{cy},"
                                f"scale=iw*3:ih*3:flags=lanczos"),
                        str(face)], check=True)
        fulls.append(full)
        faces.append(face)
        print(f"  {r['tag']:>9}  {r['w']}x{r['h']}  ({r['w']*r['h']/1e6:.2f} MP)")

    for name, group in (("full", fulls), ("face", faces)):
        strip = outdir / f"{clip_id}_{name}_comparison.png"
        args = ["ffmpeg", "-v", "error", "-y"]
        for g in group:
            args += ["-i", str(g)]
        args += ["-filter_complex", f"hstack=inputs={len(group)}", str(strip)]
        subprocess.run(args, check=True)
        print(f"wrote {strip}")

    (outdir / "ORDER.txt").write_text(
        "left to right:\n" + "\n".join(
            f"  {r['tag']}  {r['w']}x{r['h']}  {r['w']*r['h']/1e6:.2f} MP  {r['path']}"
            for r in results) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("clip", help="clip id, e.g. 17C")
    ap.add_argument("--mp", nargs="*", type=float, default=DEFAULT_MP,
                    help=f"megapixel targets (default: {DEFAULT_MP})")
    ap.add_argument("--at", type=float, default=None,
                    help="timestamp to compare, in seconds (default: clip midpoint)")
    ap.add_argument("--crop", default="0.30,0.05,0.40,0.55",
                    help="face crop as relative x,y,w,h (default upper-centre)")
    ap.add_argument("--compare-only", action="store_true",
                    help="skip rendering, rebuild comparisons from existing sweep output")
    ap.add_argument("--keep-configs", action="store_true")
    args = ap.parse_args()

    if not args.compare_only:
        preflight()

    results = []
    for mp in args.mp:
        sweep_id = f"SWEEP_{args.clip}_{tag(mp)}"
        if args.compare_only:
            vids = sorted((SHARED_STORY / sweep_id).glob("*.mp4"))
            path = vids[-1] if vids else None
            if path is None:
                print(f"  no existing output for {sweep_id}, skipping")
                continue
        else:
            cfg_path, sweep_id = build_config(args.clip, mp)
            try:
                path = render(cfg_path, sweep_id)
            finally:
                if not args.keep_configs:
                    cfg_path.unlink(missing_ok=True)
            if path is None:
                continue
        w, h, dur = probe(path)
        results.append(dict(tag=tag(mp), mp=mp, path=path, w=w, h=h, dur=dur))

    if not results:
        print("no renders to compare")
        return 1

    at = args.at if args.at is not None else round(results[0]["dur"] / 2, 2)
    print(f"\n=== comparison at t={at}s ===")
    compare(args.clip, results, at, args.crop)

    print("\nWhat to look for: whether Kent's mustache, hairline and brow become")
    print("stable and recognisable as the pixel count rises. If they do not, the")
    print("problem is not resolution and the prompt work matters more.")
    print("Note the render time and VRAM at each size - the largest one that fits")
    print("and holds identity is the setting to adopt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
