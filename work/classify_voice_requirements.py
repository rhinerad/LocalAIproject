#!/usr/bin/env python3
"""Decide which characters need a voice master, and which node renders each clip.

THE OPERATOR'S RULE, 2026-08-18
-------------------------------
Verbatim:

    "if there are characters that only have a spoken part in one generation of
    video then we dont need to remember their voice and that video can be
    generated with regular image to video minimax. If there is a scene where
    there is only one generation of spoken part for a character but there is also
    a character that has more then one spoken part within all the generations;
    this will be generated in the minimax audio/video/image to video generator.
    The character that has only one spoke part in one generation does not need an
    audio reference."

WHY IT IS RIGHT
---------------
A voice master exists for exactly one purpose: to make a character sound the same
in clip 7 as they did in clip 3. A character who speaks in **one** clip has
nothing to be consistent with. Their voice is whatever that single render
produces, and it cannot contradict itself.

So the rule is:

    speaks in 2+ clips  ->  RECURRING  ->  needs a voice master, gets <Audio N>
    speaks in 1 clip    ->  ONE-OFF    ->  needs nothing, gets no <Audio N>

And the routing follows from it:

    no recurring speaker in the clip  ->  fl2va  (MiniMaxH3ImageToVideo)
                                          plain image-to-video+audio, no refs
    any recurring speaker             ->  ref2va (MiniMaxH3ReferenceToVideo)
                                          refs for the RECURRING speakers ONLY

A mixed clip still goes through ref2va, because the recurring character in it
must stay consistent — but the one-off character in that same clip gets no
`<Audio N>` entry, no `retention_analysis` audio line, and no socket.

WHAT THIS SAVES
---------------
Measured on this film: **8 of 18 speakers are one-offs.** Six of them are among
the eight the runbook had queued as "provisional masters", so Job 2 collapses
from 8 characters to 2. The audition list drops from 17 to 9.

Four clips have no recurring speaker at all and leave the reference path
entirely: `01B`, `20B`, `22B`, `30B`.

EVIDENCE THE fl2va PATH WORKS
-----------------------------
`17.mp4` in the good-audio folder **is clip `01B`** — one of the four. The
operator rendered it with `MiniMaxH3ImageToVideo` at 0.2 MP, 20 steps,
res_multistep/simple, denoise 1.0, and filed it under "good audio". It carries a
real AAC track.

Two honest caveats on that:

1. Its prompt still declares `<Audio 1>` and `<Audio 2>`, but the fl2va node has
   **no audio reference sockets** — so the prompt promised references the graph
   could not supply, and it worked anyway. Prompts for fl2va clips should drop
   those declarations rather than rely on the model ignoring them.
2. "Filed under good audio" is the operator's ear on the picture-and-sound as a
   whole. It is not a verified statement that both one-off voices are correct.

THIS FILE IS THE ONLY PLACE THE RULE IS IMPLEMENTED
---------------------------------------------------
Anything needing the classification reads `voice_requirements.json`. Do not
recount speakers anywhere else.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OUT = EQ / "voice_requirements.json"

RECURRING_MIN_CLIPS = 2     # speaks in this many clips or more -> needs a master

# ---------------------------------------------------------------------------
# ALIASES — deliberately EMPTY, and here to document one unresolved conflict.
#
# `Doris recording` speaks only in `22B`, so the rule makes it a one-off: no
# master, no reference, fl2va. But it is a RECORDING OF DORIS played on a device,
# and Doris is recurring with a master of her own. Under the literal rule that
# device plays back a voice generated from nothing, which will not be Doris —
# a continuity break the rule cannot see, because it counts names.
#
# Mapping it to `Doris` here would route 22B to ref2va with Doris's master and
# make the recording sound like her. That is a story decision, not a mechanical
# one, so it is NOT applied. The conflict is logged in
# `outputs/equal_shares/runtime/agent_questions.md`.
#
# To apply it: VOICE_ALIASES = {"Doris recording": "Doris"} and re-run.
VOICE_ALIASES: dict[str, str] = {}
# ---------------------------------------------------------------------------


def speaker_of(line: str) -> str:
    head = line.split("“")[0].split('"')[0]
    name = re.split(r"[,:]", head)[0].strip()
    return VOICE_ALIASES.get(name, name)


def quote_of(line: str) -> str:
    m = re.search(r"[“\"]([^”\"]*)[”\"]", line)
    return " ".join(m.group(1).split()) if m else ""


def classify(cfg: dict) -> dict:
    clips_of: dict[str, list[str]] = defaultdict(list)
    words_of: Counter = Counter()
    lines_of: Counter = Counter()
    per_clip: list[dict] = []

    for clip in cfg["clips"]:
        timing = clip.get("dialogue_timing") or []
        if not timing:
            continue
        here: list[str] = []
        for d in timing:
            name, text = speaker_of(d["line"]), quote_of(d["line"])
            if not name or not text:
                continue
            if name not in here:
                here.append(name)          # order of first vocal event
            words_of[name] += len(text.split())
            lines_of[name] += 1
        for name in here:
            clips_of[name].append(clip["id"])
        per_clip.append({"id": clip["id"], "speakers": here,
                         "scripted_seconds": float(clip.get("duration") or 0)})

    characters = {}
    for name, ids in clips_of.items():
        recurring = len(ids) >= RECURRING_MIN_CLIPS
        characters[name] = {
            "clips": ids,
            "clip_count": len(ids),
            "lines": lines_of[name],
            "words": words_of[name],
            "recurring": recurring,
            "needs_voice_master": recurring,
            "reason": (
                f"speaks in {len(ids)} clips - must stay consistent across them"
                if recurring else
                f"speaks only in {ids[0]} - nothing to be consistent with, so no "
                f"master and no <Audio N>"),
        }

    recurring = {n for n, c in characters.items() if c["recurring"]}

    for row in per_clip:
        refs = [s for s in row["speakers"] if s in recurring]
        no_ref = [s for s in row["speakers"] if s not in recurring]
        row["audio_reference_speakers"] = refs
        row["no_audio_reference_speakers"] = no_ref
        row["node"] = ("MiniMaxH3ReferenceToVideo" if refs
                       else "MiniMaxH3ImageToVideo")
        row["path"] = "ref2va" if refs else "fl2va"
        row["mixed"] = bool(refs and no_ref)
        row["why"] = (
            f'no recurring speaker; plain image-to-video, no audio references'
            if not refs else
            f'recurring: {", ".join(refs)}'
            + (f' | no reference for one-off: {", ".join(no_ref)}' if no_ref else ""))

    return {"characters": characters, "clips": per_clip,
            "recurring": sorted(recurring),
            "one_off": sorted(set(characters) - recurring)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="report only; do not write voice_requirements.json")
    args = ap.parse_args()

    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    r = classify(cfg)
    ch, clips = r["characters"], r["clips"]

    print(f'{"character":24s}{"clips":>6}{"lines":>6}{"words":>7}  master?')
    print("-" * 78)
    for name, c in sorted(ch.items(), key=lambda kv: (-kv[1]["clip_count"], -kv[1]["words"])):
        print(f'{name:24s}{c["clip_count"]:6d}{c["lines"]:6d}{c["words"]:7d}  '
              + ("YES  recurring" if c["needs_voice_master"]
                 else f'no   one-off in {c["clips"][0]}'))

    fl = [c for c in clips if c["path"] == "fl2va"]
    rf = [c for c in clips if c["path"] == "ref2va"]
    mixed = [c for c in clips if c["mixed"]]

    print(f'\nspeakers                     : {len(ch)}')
    print(f'  recurring, need a master   : {len(r["recurring"])}')
    print(f'  one-off, need nothing      : {len(r["one_off"])}  '
          f'({", ".join(r["one_off"])})')
    print(f'\ndialogue clips               : {len(clips)}')
    print(f'  fl2va, no audio reference  : {len(fl)}  ({", ".join(c["id"] for c in fl)})')
    print(f'  ref2va, references needed  : {len(rf)}')
    print(f'  of those, MIXED            : {len(mixed)}')
    for c in mixed:
        print(f'      {c["id"]:6s} refs: {", ".join(c["audio_reference_speakers"]):34s} '
              f'no ref: {", ".join(c["no_audio_reference_speakers"])}')

    total_refs = sum(len(c["audio_reference_speakers"]) for c in clips)
    over = [c for c in clips if len(c["audio_reference_speakers"]) > 3]
    print(f'\naudio reference slots used    : {total_refs}')
    print(f'clips exceeding H3\'s 3-audio limit: {len(over)}'
          + (f'  {[c["id"] for c in over]}' if over else "  (none)"))

    payload = {
        "generated_by": "work/classify_voice_requirements.py",
        "rule": ("A character who speaks in only ONE clip needs no voice master and "
                 "no <Audio N>: there is nothing for them to be consistent with. "
                 "A clip with no recurring speaker renders on plain fl2va "
                 "(MiniMaxH3ImageToVideo). A clip with any recurring speaker renders "
                 "on ref2va with references for the RECURRING speakers only."),
        "recurring_min_clips": RECURRING_MIN_CLIPS,
        "summary": {
            "speakers": len(ch),
            "recurring": len(r["recurring"]),
            "one_off": len(r["one_off"]),
            "dialogue_clips": len(clips),
            "fl2va_clips": [c["id"] for c in fl],
            "ref2va_clips": len(rf),
            "mixed_clips": [c["id"] for c in mixed],
            "audio_reference_slots": total_refs,
        },
        **r,
    }
    if args.check:
        print("\n--check: nothing written")
    else:
        OUT.write_text(json.dumps(payload, indent=2), encoding="utf8")
        print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
