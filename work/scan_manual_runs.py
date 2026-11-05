"""Reconstruct the manual ComfyUI session from ComfyUI's own PNG metadata.

Every generation in the manual workflow writes a PNG alongside the video, and
ComfyUI embeds the whole API graph in that PNG's `prompt` text chunk. So the
manual session is fully recoverable: which clip, which anchors, what duration,
what aspect ratio, what seed, how many steps, and whether the prompt arrived
wrapped in stray quotation marks.

This is read-only. It touches nothing but the PNGs.

Usage (from the folder containing outputs\\ and work\\):
    python work\\scan_manual_runs.py
    python work\\scan_manual_runs.py --since 2026-08-10T18:00
    python work\\scan_manual_runs.py --json manual_runs.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("requires pillow: pip install pillow")

SHARED_OUT = r"A:\Users\rhine\ComfyUI-Shared\output"
CONFIG = os.path.join("outputs", "equal_shares", "story_config.json")


def anchor_index(config_path):
    """basename without extension -> {(clip_id, slot)}"""
    with open(config_path, encoding="utf-8-sig") as fh:
        clips = json.load(fh)["clips"]
    idx, by_pair = {}, {}
    for c in clips:
        f = c.get("first_frame")
        l = c.get("last_frame")
        for slot, path in (("first", f), ("last", l)):
            if path:
                base = os.path.splitext(os.path.basename(path.replace("\\", "/")))[0]
                idx.setdefault(base, set()).add((c["id"], slot))
        if f and l:
            by_pair[(os.path.splitext(os.path.basename(f.replace("\\", "/")))[0],
                     os.path.splitext(os.path.basename(l.replace("\\", "/")))[0])] = c["id"]
    return idx, by_pair, {c["id"]: c for c in clips}


def read_graph(png):
    try:
        info = Image.open(png).info
    except Exception:
        return None
    raw = info.get("prompt")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def nodes(graph, cls):
    return [v["inputs"] for v in graph.values()
            if isinstance(v, dict) and v.get("class_type") == cls and "inputs" in v]


def describe(graph, by_pair, idx):
    li = [os.path.splitext(n["image"])[0].split("__")[-1] for n in nodes(graph, "LoadImage")]
    res = (nodes(graph, "ResolutionSelector") or [{}])[0]
    sch = (nodes(graph, "BasicScheduler") or [{}])[0]
    noise = (nodes(graph, "RandomNoise") or [{}])[0]
    dur = (nodes(graph, "PrimitiveFloat") or [{}])[0].get("value")
    h3 = (nodes(graph, "MiniMaxH3ImageToVideo") or [{}])[0]
    text = h3.get("prompt", "") if isinstance(h3.get("prompt"), str) else ""

    clip = by_pair.get(tuple(li)) if len(li) == 2 else None
    if clip is None:
        cands = set()
        for b in li:
            cands |= {c for c, _ in idx.get(b, ())}
        clip = "/".join(sorted(cands)) + " (no configured pair)" if cands else "unknown"

    return dict(clip=clip, anchors=li, duration=dur,
                aspect_ratio=res.get("aspect_ratio"), megapixels=res.get("megapixels"),
                multiple=res.get("multiple"), steps=sch.get("steps"),
                denoise=sch.get("denoise"), seed=noise.get("noise_seed"),
                prompt_chars=len(text),
                prompt_wrapped_in_quotes=text.startswith('"') and text.endswith('"'))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shared-output", default=SHARED_OUT)
    ap.add_argument("--config", default=CONFIG)
    ap.add_argument("--since", default=None, help="ISO time, e.g. 2026-08-10T18:00")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.config):
        return f"config not found: {args.config}" and 2
    idx, by_pair, clips = anchor_index(args.config)

    cutoff = 0.0
    if args.since:
        cutoff = dt.datetime.fromisoformat(args.since).timestamp()

    videos = {os.path.getmtime(v): os.path.basename(v)
              for v in glob.glob(os.path.join(args.shared_output, "video", "*.mp4"))}

    runs = []
    for png in sorted(glob.glob(os.path.join(args.shared_output, "ComfyUI_*.png"))):
        t = os.path.getmtime(png)
        if t < cutoff:
            continue
        g = read_graph(png)
        if not g:
            continue
        row = describe(g, by_pair, idx)
        row["time"] = dt.datetime.fromtimestamp(t).isoformat(timespec="minutes")
        row["png"] = os.path.basename(png)
        row["kept_video"] = next((n for vt, n in videos.items() if abs(vt - t) < 90), "")
        runs.append(row)

    if not runs:
        print("no manual runs found")
        return 0

    print(f"{'time':17}{'clip':<34}{'aspect':<20}{'dur':>6}{'MP':>6}{'steps':>6}{'quoted':>8}  kept")
    for r in runs:
        warn = "  <-- SQUARE" if r["aspect_ratio"] and "1:1" in r["aspect_ratio"] else ""
        print(f"{r['time']:17}{str(r['clip']):<34}{str(r['aspect_ratio']):<20}"
              f"{str(r['duration']):>6}{str(r['megapixels']):>6}{str(r['steps']):>6}"
              f"{str(r['prompt_wrapped_in_quotes']):>8}  {r['kept_video']}{warn}")

    kept = sum(1 for r in runs if r["kept_video"])
    print(f"\nattempts {len(runs)} | videos kept {kept} | keep rate {kept/len(runs)*100:.0f}%")
    sq = sum(1 for r in runs if r["aspect_ratio"] and "1:1" in r["aspect_ratio"])
    q = sum(1 for r in runs if r["prompt_wrapped_in_quotes"])
    if sq:
        print(f"WARNING: {sq} run(s) used 1:1 (Square). The saved workflow ships with that value.")
    if q:
        print(f"WARNING: {q} run(s) sent a prompt wrapped in quotation marks. That usually means")
        print("         the text was copied out of the raw CSV, where fields are quote-escaped.")
        print("         Copy from prompts\\<clip>.txt instead.")

    last = runs[-1]
    order = [c["id"] for c in json.load(open(args.config, encoding="utf-8-sig"))["clips"]]
    cid = str(last["clip"]).split(" ")[0]
    if cid in order and order.index(cid) + 1 < len(order):
        print(f"\nLast clip worked: {cid} at {last['time']}")
        print(f"Next clip in story order: {order[order.index(cid)+1]}")

    if args.json:
        json.dump(runs, open(args.json, "w", encoding="utf-8"), indent=2)
        print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
