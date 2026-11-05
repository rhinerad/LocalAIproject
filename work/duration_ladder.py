#!/usr/bin/env python3
"""The DURATION LADDER — how to retry a take that speaks badly.

THE OPERATOR'S RULE, 2026-08-18
-------------------------------
Verbatim:

    "when generating audio and trying to get perfect English words (getting rid
    of gibberish or mispronounced words) use this generation pattern. Example
    start at 10 sec; if gen is bad (has mispronounced words) add a second. If
    that does not work go back to 10 and go down to 9 seconds. The pattern of
    generation to fix gibberish and mispronounced words is the following;
    10, 11, 9, 12, 8, 13, 7 and so forth."

So from a base length D the rungs are:

    rung 0   D
    rung 1   D + 1
    rung 2   D - 1
    rung 3   D + 2
    rung 4   D - 2
    rung 5   D + 3
    rung 6   D - 3
    ...

Alternating outward, up first, one second at a time.

WHY THIS IS THE RIGHT KNOB — AND WHY THE SEED IS NOT
----------------------------------------------------
H3 generates audio and video jointly across one latent whose size is fixed by
the frame count. The number of words is fixed by the script. So the *speech
rate the model must hit* is words / duration, and that quantity is set entirely
by the duration — the seed does not change it.

When the required rate is wrong for the model, it does not slow down or leave a
gap. It slurs, elides, mispronounces, or invents syllables to fill the metre.
Re-rolling the seed asks the same impossible rate again with different noise,
which is why re-rolling has produced a different flavour of gibberish rather
than clean speech. Moving one second changes the rate by roughly 10% and gives
the model a metre it can actually speak.

Up first because a fractionally slow delivery is natural and a rushed one is
not; down afterwards because an over-long window is the other failure mode.

THE 17-FRAME BLOCK GRID
-----------------------
H3 snaps duration to frame counts congruent to 5 modulo 17 at 24 fps, and this
project rounds UP to the next legal value (CLAUDE.md, "not negotiable"). One
block is 17/24 = 0.708 s, so a nominal one-second step lands one or two blocks
away and the realised step is between 0.71 s and 1.42 s. The rungs are always
distinct and always ordered; they are simply not exactly one second apart. From
a nominal base of 10 s:

    rung 0   10 s ->  243 f  = 10.125 s
    rung 1   11 s ->  277 f  = 11.542 s
    rung 2    9 s ->  226 f  =  9.417 s
    rung 3   12 s ->  294 f  = 12.250 s
    rung 4    8 s ->  192 f  =  8.000 s
    rung 5   13 s ->  328 f  = 13.667 s
    rung 6    7 s ->  175 f  =  7.292 s

BOUNDS
------
`max_seconds` — the clip's SCRIPTED duration. A Stage-1 soundtrack is padded
with digital silence up to the scripted length at assembly, so a soundtrack
longer than the picture cannot be used. Upward rungs past it are skipped, not
clamped; clamping would render the same length twice and waste a rung.

`min_seconds` — MIN_FLOOR by default. Below this there is not enough window for
the words at any plausible pace and the tail gets cut off mid-word.

Skipped rungs are dropped from the sequence entirely, so a clip whose base
already equals its scripted length gets a purely downward ladder.

THE VALIDATOR INTERACTION — READ THIS
-------------------------------------
`work/validate_audio_take.py` raises WRONG_LENGTH when a render is longer than
`audio_pass_durations.json` allows. Every upward rung is longer than that by
design. Anything driving this ladder MUST pass the rung's own length to the
validator (`--configured-seconds`) or it will reject its own correct retries.

WHAT IS NOT CLAIMED
-------------------
That this ladder fixes mispronunciation. It is the operator's rule, derived from
their own hand-rendering, and it is implemented here exactly as given. No render
has yet been made under it. Nothing in this file has been diffed against
`docs/GOLDEN_REFERENCE/PROVEN_GOOD_AUDIO_GRAPH.api.json` because it does not
change the graph — only the `length` value fed to it.

Evidence that duration is at least a live variable: the 14 known-good clips run
7.0 / 9.0 / 9.0 / 10.0 / 10.0 / 11.0 s and were arrived at by hand.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FPS = 24
BLOCK = 17
PHASE = 5
STEP_SECONDS = 1.0     # the operator's step; one nominal second per rung
MIN_FLOOR = 3.0        # never render a soundtrack shorter than this
MAX_RUNGS = 9          # 0..8 == base, +-1, +-2, +-3, +-4


def frames_for(seconds: float) -> int:
    """Round UP to the next frame count congruent to 5 modulo 17, at 24 fps.

    Identical to the expression embedded in the proven-good graph:
        max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17
    """
    base = max(PHASE, round(seconds * FPS))
    return base + (PHASE - (base % BLOCK)) % BLOCK


def nominal_for_rung(base_seconds: float, rung: int) -> float:
    """The operator's sequence: D, D+1, D-1, D+2, D-2, D+3, D-3, ..."""
    if rung <= 0:
        return base_seconds
    magnitude = (rung + 1) // 2
    direction = 1 if rung % 2 == 1 else -1
    return base_seconds + direction * magnitude * STEP_SECONDS


def ladder(base_seconds: float,
           max_seconds: float | None = None,
           min_seconds: float = MIN_FLOOR,
           rungs: int = MAX_RUNGS,
           max_frames: int | None = None) -> list[dict]:
    """The full retry sequence for one clip, in the order it must be tried.

    Returns one row per USABLE rung. Rungs outside the bounds, and rungs that
    quantize onto a frame count already used by an earlier rung, are omitted --
    rendering the same frame count twice is a wasted attempt, not a retry.

    CEILING: PREFER `max_frames`. Both the soundtrack and the picture are snapped
    to the 17k+5 grid, so the real ceiling is the clip's scripted FRAME COUNT, not
    its scripted seconds.

    Comparing seconds was wrong and measurably so. A clip scripted at 15.0 s
    renders 362 frames = 15.083 s of picture. Its fitted soundtrack base is also
    362 frames -- but 15.083 > 15.0, so a seconds-based cap threw the BASE RUNG
    away. Measured 2026-08-18: **51 of 124 clips would have skipped their own base
    duration** and opened the ladder at rung 2 (base minus one second), rendering
    every already-tight clip short on the first attempt.

    `max_seconds` is still honoured when `max_frames` is absent, for ad-hoc use.
    """
    out: list[dict] = []
    seen: set[int] = set()
    for r in range(rungs):
        nominal = nominal_for_rung(base_seconds, r)
        if nominal < min_seconds:
            continue
        frames = frames_for(nominal)
        seconds = frames / FPS
        if max_frames is not None:
            if frames > max_frames:
                continue
        elif max_seconds is not None and seconds > max_seconds + 1e-9:
            continue
        if frames in seen:
            continue
        seen.add(frames)
        out.append({
            "rung": r,
            "nominal_seconds": round(nominal, 3),
            "frames": frames,
            "seconds": round(seconds, 3),
            "delta_from_base": round(seconds - frames_for(base_seconds) / FPS, 3),
        })
    return out


def rung_for_attempt(base_seconds: float, attempt_number: int,
                     max_seconds: float | None = None,
                     min_seconds: float = MIN_FLOOR,
                     max_frames: int | None = None) -> dict:
    """Length for attempt N, 1-based. Attempt 1 is always the base.

    If the ladder runs out of usable rungs the last one repeats, so a caller
    cannot crash on an over-long retry loop; the repetition is visible in the
    returned row via `exhausted`.
    """
    rows = ladder(base_seconds, max_seconds, min_seconds, max_frames=max_frames)
    if not rows:                                    # bounds admit nothing
        frames = frames_for(max(min_seconds, base_seconds))
        return {"rung": 0, "nominal_seconds": base_seconds, "frames": frames,
                "seconds": round(frames / FPS, 3), "delta_from_base": 0.0,
                "exhausted": True}
    index = max(0, attempt_number - 1)
    row = dict(rows[min(index, len(rows) - 1)])
    row["exhausted"] = index >= len(rows)
    return row


def _main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seconds", type=float, help="base length for an ad-hoc ladder")
    ap.add_argument("--max-seconds", type=float, default=None)
    ap.add_argument("--clip", help="read the base length from audio_pass_durations.json")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    base, cap, capf = args.seconds, args.max_seconds, None
    if args.clip:
        eq = Path(__file__).resolve().parents[1] / "outputs" / "equal_shares"
        rows = json.loads((eq / "audio_pass_durations.json").read_text(encoding="utf8"))
        for r in rows["clips"]:
            if r["id"] == args.clip:
                base = float(r["audio_pass_seconds"])
                cap = float(r["scripted_seconds"])
                capf = int(r["scripted_frames"])
                break
        else:
            print(f"no such clip: {args.clip}")
            return 2
    if base is None:
        ap.error("give --seconds or --clip")

    rows = ladder(base, cap, max_frames=capf)
    if args.json:
        print(json.dumps({"base_seconds": base, "max_seconds": cap, "max_frames": capf, "rungs": rows}, indent=2))
        return 0

    label = args.clip or f"{base}s"
    print(f"{label}  base {base:.3f}s" + (f"  cap {cap:.3f}s" if cap else ""))
    print(f"{'try':>4}{'rung':>6}{'nominal':>10}{'frames':>8}{'actual':>9}")
    for i, r in enumerate(rows, 1):
        print(f'{i:4d}{r["rung"]:6d}{r["nominal_seconds"]:10.2f}'
              f'{r["frames"]:8d}{r["seconds"]:9.3f}')
    if not rows:
        print("   no usable rung — bounds admit nothing")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
