"""Compare accepted takes against rejected ones, using ComfyUI's own metadata.

ComfyUI writes a PNG beside every generation with the complete API graph embedded
in it. Keepers get moved or renamed into output\\video\\; rejects are deleted. So a
PNG whose timestamp has no surviving video is a rejected take, and the PNG still
holds everything about it: the exact prompt, both anchor filenames, seed, steps,
resolution, duration, sampler, scheduler and every model path.

That makes the whole session a controlled experiment after the fact. This groups
takes by clip and shows what actually differed between the ones that worked and
the ones that did not.

Re-run it as you generate; it reads the current state each time.

USAGE
    python work\\analyze_takes.py
    python work\\analyze_takes.py --since 2026-08-11T12:00
    python work\\analyze_takes.py --clip 00D --diff
    python work\\analyze_takes.py --csv takes.csv --json takes.json
"""

from __future__ import annotations

import argparse
import csv as csvmod
import datetime as dt
import difflib
import glob
import json
import os
import subprocess
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("requires pillow")

SHARED_OUT = r"A:\Users\rhine\ComfyUI-Shared\output"
CONFIG = os.path.join("outputs", "equal_shares", "story_config.json")
MATCH_WINDOW = 90   # seconds between a PNG and its video
DUR_TOL = 0.2       # a real keeper's duration must equal frames/24


def node_inputs(graph, cls):
    return [v["inputs"] for v in graph.values()
            if isinstance(v, dict) and v.get("class_type") == cls and "inputs" in v]


def anchor_map(config_path):
    if not os.path.exists(config_path):
        return {}
    with open(config_path, encoding="utf-8-sig") as fh:
        clips = json.load(fh)["clips"]
    out = {}
    for c in clips:
        f, l = c.get("first_frame"), c.get("last_frame")
        key = tuple(os.path.splitext(os.path.basename((p or "").replace("\\", "/")))[0]
                    for p in (f, l) if p)
        if key:
            out[key] = c["id"]
    return out


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height",
                        "-show_entries", "format=duration",
                        "-of", "csv=p=0:nk=1", path], capture_output=True, text=True)
    # csv output puts "w,h" on one line and the duration on the next, so split
    # on commas as well as newlines before indexing.
    parts = r.stdout.replace(",", "\n").split()
    try:
        return f"{parts[0]}x{parts[1]}", float(parts[2])
    except Exception:
        return "?", 0.0


def collect(shared, config_path, since):
    amap = anchor_map(config_path)
    videos = []
    for v in glob.glob(os.path.join(shared, "video", "*.mp4")):
        _, vd = probe(v)
        videos.append((os.path.getmtime(v), v, vd))

    takes = []
    for png in sorted(glob.glob(os.path.join(shared, "ComfyUI_*.png"))):
        t = os.path.getmtime(png)
        if since and t < since:
            continue
        try:
            g = json.loads(Image.open(png).info.get("prompt", "{}"))
        except Exception:
            continue
        h3 = node_inputs(g, "MiniMaxH3ImageToVideo")
        if not h3:
            continue
        res = (node_inputs(g, "ResolutionSelector") or [{}])[0]
        sch = (node_inputs(g, "BasicScheduler") or [{}])[0]
        noise = (node_inputs(g, "RandomNoise") or [{}])[0]
        dur = (node_inputs(g, "PrimitiveFloat") or [{}])[0].get("value")
        imgs = [os.path.splitext(n["image"])[0].split("__")[-1] for n in node_inputs(g, "LoadImage")]
        # Wiring checks. A LoadImage node can sit in the graph fully loaded and
        # never be connected to the model -- the anchor is then silently ignored,
        # and anyone appearing only in that frame is invented from nothing.
        loads = {k: v["inputs"].get("image") for k, v in g.items()
                 if isinstance(v, dict) and v.get("class_type") == "LoadImage"}
        ff, lf = h3[0].get("first_frame"), h3[0].get("last_frame")
        first_img = loads.get(ff[0]) if isinstance(ff, list) else None
        last_img = loads.get(lf[0]) if isinstance(lf, list) else None
        last_wired = last_img is not None
        anchors_same = bool(first_img and first_img == last_img)
        loaded_but_unused = len(loads) >= 2 and not last_wired
        prompt = h3[0].get("prompt") if isinstance(h3[0].get("prompt"), str) else ""

        # Match a take to a surviving video by BOTH timestamp proximity and
        # duration. Timestamp alone produced a false pairing: a Clipchamp export
        # that happened to land near a generation was read as its keeper.
        base = max(5, round((dur or 0) * 24))
        expect = (base + (5 - (base % 17)) % 17) / 24.0
        kept = None
        for vt, v, vd in videos:
            if abs(vt - t) < MATCH_WINDOW and abs(vd - expect) < 0.2:
                kept = v
                break
        takes.append(dict(
            png=os.path.basename(png), time=dt.datetime.fromtimestamp(t).isoformat(timespec="minutes"),
            clip=amap.get(tuple(imgs), "/".join(imgs)), anchors=imgs,
            accepted=bool(kept), video=os.path.basename(kept) if kept else "",
            duration=dur, aspect=res.get("aspect_ratio"), megapixels=res.get("megapixels"),
            steps=sch.get("steps"), denoise=sch.get("denoise"), seed=noise.get("noise_seed"),
            prompt=prompt, prompt_chars=len(prompt),
            prompt_wrapped=prompt.startswith('"') and prompt.endswith('"'),
            last_frame_wired=last_wired, anchors_identical=anchors_same,
            anchor_loaded_but_unused=loaded_but_unused,
        ))
    return takes


def summarise(takes):
    by = {}
    for t in takes:
        by.setdefault(t["clip"], []).append(t)

    print(f"{'clip':<34}{'takes':>6}{'kept':>6}  what changed on the keeper")
    for clip, group in sorted(by.items(), key=lambda kv: kv[1][0]["time"]):
        acc = [t for t in group if t["accepted"]]
        rej = [t for t in group if not t["accepted"]]
        notes = []
        if acc and rej:
            for field in ("megapixels", "aspect", "steps", "duration", "prompt_chars", "prompt_wrapped"):
                av = {t[field] for t in acc}
                rv = {t[field] for t in rej}
                if av and av != rv and not (av & rv):
                    notes.append(f"{field}: kept {sorted(av)} vs rejected {sorted(rv)}")
            seeds_a = {t["seed"] for t in acc}
            if len(group) > 1 and len({t["prompt"] for t in group}) == 1:
                notes.append("prompt identical across all takes - only the seed varied")
            elif len({t["prompt"] for t in group}) > 1:
                notes.append(f"{len({t['prompt'] for t in group})} distinct prompt versions tried")
        if not acc:
            notes.append("no keeper yet")
        print(f"{clip:<34}{len(group):>6}{len(acc):>6}  {'; '.join(notes) if notes else '-'}")

    tot, kept = len(takes), sum(1 for t in takes if t["accepted"])
    print(f"\n{tot} takes, {kept} kept ({kept/tot*100:.0f}%)")
    unused = [t for t in takes if t["anchor_loaded_but_unused"]]
    if unused:
        print(f"\nWIRING FAULT: {len(unused)} take(s) loaded a second anchor image that was never")
        print("connected to the model. Anyone who appears only in that frame was invented.")
        span = f"{unused[0]['time']} .. {unused[-1]['time']}"
        print(f"  affected: {span}")
        print("  " + " ".join(t["png"].replace("ComfyUI_", "").replace("_.png", "") for t in unused))
    same = [t for t in takes if t["anchors_identical"]]
    if same:
        print(f"\n{len(same)} take(s) used the SAME image as both first and last frame:")
        print("  " + " ".join(t["png"].replace("ComfyUI_", "").replace("_.png", "") for t in same))
    q = sum(1 for t in takes if t["prompt_wrapped"])
    if q:
        acc_q = sum(1 for t in takes if t["prompt_wrapped"] and t["accepted"])
        print(f"{q} take(s) sent a quote-wrapped prompt; {acc_q} of those were kept")
    return by


def show_diff(by, clip):
    group = by.get(clip)
    if not group:
        print(f"no takes for {clip}")
        return
    acc = [t for t in group if t["accepted"]]
    rej = [t for t in group if not t["accepted"]]
    if not acc or not rej:
        print(f"{clip}: need both an accepted and a rejected take to diff")
        return
    a, r = acc[-1], rej[-1]
    print(f"\n=== {clip}: last rejected ({r['png']}) -> kept ({a['png']}) ===")
    for f in ("duration", "megapixels", "aspect", "steps", "seed", "prompt_chars"):
        if a[f] != r[f]:
            print(f"  {f}: {r[f]} -> {a[f]}")
    if a["prompt"] != r["prompt"]:
        print("  prompt changed:")
        for line in list(difflib.unified_diff(r["prompt"].splitlines(), a["prompt"].splitlines(),
                                              "rejected", "kept", lineterm="", n=1))[:40]:
            print("   ", line)
    else:
        print("  prompt identical")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shared-output", default=SHARED_OUT)
    ap.add_argument("--config", default=CONFIG)
    ap.add_argument("--since")
    ap.add_argument("--clip")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    args = ap.parse_args()

    since = dt.datetime.fromisoformat(args.since).timestamp() if args.since else 0
    takes = collect(args.shared_output, args.config, since)
    if not takes:
        print("no takes found")
        return 1
    by = summarise(takes)
    if args.clip:
        show_diff(by, args.clip)
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            w = csvmod.DictWriter(fh, fieldnames=[k for k in takes[0] if k not in ("prompt", "anchors")])
            w.writeheader()
            for t in takes:
                w.writerow({k: v for k, v in t.items() if k not in ("prompt", "anchors")})
        print(f"\nwrote {args.csv}")
    if args.json:
        json.dump(takes, open(args.json, "w", encoding="utf-8"), indent=2)
        print(f"wrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
