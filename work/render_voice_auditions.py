#!/usr/bin/env python3
"""Render the voice auditions so the operator can choose every recurring voice.

WHY THIS RUNS BEFORE THE 124-CLIP PASS
--------------------------------------
Only the Narrator has an approved voice. Every other master on disk was cut from
a take nobody listened to, and the operator reports several speak gibberish. A
bad master poisons every clip that references it, so the soundtrack pass is
worthless until the voices are chosen. This is the gate.

WHAT AN AUDITION IS
-------------------
The character's longest line, rendered **with no audio reference wired at all**.
There is no voice to match yet — referencing an unapproved master would lock in
the very voice we are trying to replace. H3 invents a voice from the written
description in the prompt, three seeds per character, and the operator picks.

Nine characters, three takes each: **27 renders at 0.2 MP.** The one-off rule
(2026-08-18) removed eight characters who speak in a single clip and therefore
need no master at all.

THE TWO KNOBS, AND ONLY ONE PER ATTEMPT
---------------------------------------
  wrong VOICE (timbre, age, accent)  ->  change the SEED. This is the one place
                                         in the project where re-rolling is right.
  wrong WORDS (gibberish, slurring)  ->  walk the DURATION LADDER. Words per
                                         second is fixed by the line and the
                                         window; the seed cannot move it.

This runner does the seed sweep. If a take has the right voice but bad words,
re-run that one character with `--character X --ladder-rung N` holding the seed.

SAFETY
------
One backend per render, stopped afterwards, thermal guard before and after —
identical to the soundtrack pass. Claims the same `render_queue_owner.json` lock,
so it can never run beside the main pass.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from datetime import datetime
from pathlib import Path

import duration_ladder
import render_single_pass as h3
import thermal_guard

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
PACKS = Path(r"A:\Users\rhine\Desktop\EQUAL_SHARES_VOICE_AUDITIONS")
MANIFEST = EQ / "voice_audition_manifest.json"
OWNER = EQ / "runtime" / "render_queue_owner.json"
LOG = EQ / "runtime" / "voice_audition.log"

MEGAPIXELS = 0.2
TAKES_DEFAULT = 3


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def claim_queue() -> bool:
    """One GPU owner, ever. Same lock file as the soundtrack pass."""
    if OWNER.exists():
        try:
            pid = int(json.loads(OWNER.read_text(encoding="utf-8-sig")).get("pid", 0))
        except Exception:
            pid = 0
        if pid and pid != os.getpid() and h3.process_exists(pid):
            emit(f"queue belongs to live pid={pid}; refusing to start a second backend")
            return False
    OWNER.parent.mkdir(parents=True, exist_ok=True)
    OWNER.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Equal Shares voice auditions — 0.2 MP, no audio reference",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    OWNER.write_text(json.dumps({
        "pid": 0, "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text(encoding="utf-8-sig"))
    return {"purpose": "voice auditions — operator picks one take per character",
            "characters": {}}


def save_manifest(d: dict) -> None:
    tmp = MANIFEST.with_suffix(f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, MANIFEST)


def stage_first_frame(folder: Path) -> str:
    """Copy the pack's first frame into ComfyUI's input dir. Returns its name."""
    for cand in sorted(folder.glob("first_frame.*")):
        h3.SHARED_INPUT.mkdir(parents=True, exist_ok=True)
        name = f"audition_{folder.name}{cand.suffix}"
        dst = h3.SHARED_INPUT / name
        if not dst.exists():
            shutil.copy2(cand, dst)
        return name
    raise FileNotFoundError(f"no first_frame.* in {folder}")


def build_workflow(prompt: str, frames: int, first_file: str, seed: int,
                   out_prefix: str) -> dict:
    """fl2va with NO reference sockets — the audition has no voice to match.

    Deliberately the same node, checkpoint and settings as `17.mp4`, the one
    proven fl2va render on this machine. `_common_nodes` takes seconds and
    re-derives the frame count with the project's 17k+5 expression, so passing
    frames/24 round-trips exactly.
    """
    wf = h3.build_fl2va_workflow(
        "audition", frames / 24.0, first_file, prompt, seed, out_prefix,
    )
    wf["115"]["inputs"]["megapixels"] = MEGAPIXELS
    return wf


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--packs", default=str(PACKS))
    ap.add_argument("--character", action="append",
                    help="render only this pack folder name; repeatable")
    ap.add_argument("--takes", type=int, default=TAKES_DEFAULT)
    ap.add_argument("--ladder-rung", type=int, default=0,
                    help="render at this ladder rung instead of the base. Use when "
                         "the voice is right but the words are wrong; keep --seed.")
    ap.add_argument("--seed", type=int, default=None,
                    help="fix the seed (required when walking the ladder)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    packs = Path(args.packs)
    index_path = packs / "index.json"
    if not index_path.is_file():
        emit(f"no index.json in {packs} — run work/build_voice_auditions.py first")
        return 2
    index = json.loads(index_path.read_text(encoding="utf8"))
    if args.character:
        wanted = {c.lower() for c in args.character}
        index = [e for e in index
                 if e["folder"].lower() in wanted or e["character"].lower() in wanted]
        if not index:
            emit(f"no pack matched {args.character}")
            return 2

    total = len(index) * args.takes
    emit(f"voice auditions: {len(index)} characters x {args.takes} takes = {total} renders "
         f"at {MEGAPIXELS} MP, ladder rung {args.ladder_rung}")

    if args.dry_run:
        for e in index:
            L = duration_ladder.ladder(e["seconds"])
            rung = L[min(args.ladder_rung, len(L) - 1)]
            emit(f'  {e["character"]:24s} {e["words"]:3d}w  '
                 f'{rung["frames"]:4d}f = {rung["seconds"]:6.2f}s  from {e["source_clip"]}')
        emit("--dry-run: nothing rendered")
        return 0

    if not claim_queue():
        return 1

    manifest = load_manifest()
    comfy_pid = None
    done = 0
    try:
        for e in index:
            folder = packs / e["folder"]
            prompt = (folder / "prompt.txt").read_text(encoding="utf8").strip()
            if not prompt.startswith("subject_definitions:"):
                emit(f'{e["character"]}: prompt does not start with subject_definitions: — skipping')
                continue
            if "<Audio" in prompt:
                emit(f'{e["character"]}: prompt contains <Audio — an audition must have '
                     f'no reference. Skipping rather than locking in an unapproved voice.')
                continue

            first_file = stage_first_frame(folder)
            rungs = duration_ladder.ladder(e["seconds"])
            rung = rungs[min(args.ladder_rung, len(rungs) - 1)]

            rec = manifest["characters"].setdefault(e["character"], {
                "slug": e["slug"], "source_clip": e["source_clip"],
                "line": e["line"], "words": e["words"], "takes": [],
                "chosen": None, "status": "awaiting_operator_choice",
            })

            for t in range(args.takes):
                seed = args.seed if args.seed is not None else random.randint(0, 2**53)
                tag = f'{e["slug"]}_r{rung["rung"]}_t{t+1:02d}'
                done += 1
                emit(f'[{done}/{total}] {e["character"]}: rung {rung["rung"]} '
                     f'{rung["seconds"]:.2f}s / {rung["frames"]}f, seed={seed}')

                if h3.api_ready():
                    if comfy_pid is None:
                        emit("port 8188 held by an unowned backend; stopping")
                        return 1
                    h3.stop_comfy(comfy_pid)
                    comfy_pid = None
                    thermal_guard.wait_after_render(emit)
                thermal_guard.wait_before_render(emit)
                comfy_pid = h3.start_comfy()

                take = {"take": t + 1, "seed": seed, "ladder_rung": rung["rung"],
                        "frames": rung["frames"], "seconds": rung["seconds"],
                        "megapixels": MEGAPIXELS, "audio_reference": None,
                        "started_at": datetime.now().isoformat(timespec="seconds")}
                try:
                    wf = build_workflow(prompt, rung["frames"], first_file, seed,
                                        f"story/AUDITION_{e['slug']}/{tag}")
                    pid_ = h3.submit_workflow(wf)
                    outs = h3.wait_for_completion(pid_, tag)
                    video = h3.find_video_output(outs)
                    take.update(status="rendered" if video else "no_output",
                                source_video=video,
                                completed_at=datetime.now().isoformat(timespec="seconds"))
                except Exception as exc:
                    take.update(status="render_error", error=str(exc))

                rec["takes"].append(take)
                save_manifest(manifest)
                emit(f'   {tag}: {take["status"]}')
    finally:
        if comfy_pid is not None and h3.api_ready():
            h3.stop_comfy(comfy_pid)
        thermal_guard.wait_after_render(emit)
        release_queue()

    ok = sum(1 for r in manifest["characters"].values()
             for t in r["takes"] if t.get("status") == "rendered")
    emit(f"auditions finished: {ok}/{total} rendered")
    emit(f"manifest -> {MANIFEST}")
    emit("NEXT: the operator listens and picks one take per character. "
         "Nothing is chosen automatically — this runner cannot hear. "
         "Then run work/install_audition_winners.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
