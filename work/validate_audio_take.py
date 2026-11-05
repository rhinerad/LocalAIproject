#!/usr/bin/env python3
"""Mechanically score a Stage-1 soundtrack take, so an agent need not ask.

WHY THIS EXISTS
---------------
The acceptance criteria for a soundtrack take are "by ear": correct words, one
dry voice, no invented speech after the line. An autonomous agent has no ears,
so it either stalls waiting for a human or guesses. Both are bad.

This scores the two failure modes that ARE measurable, so the agent can keep
rendering and only surface takes that genuinely need a human.

  WRONG_LENGTH  the take was rendered longer than audio_pass_durations.json
                allows. This is the real cause of tail gibberish: H3 fills the
                window it is given, so an over-long render guarantees invented
                speech. Catching it here stops a whole pass being wasted on a
                stale frame count.

  INVENTED      total speech far longer than the words can account for, measured
                against words / WORDS_PER_SEC.

  SILENCE       too little speech to be the scripted line at all.

**A take that fills its window is NOT a fault** once the window is the right
size — that is the entire point of shortening the render. Calibrated against the
known-good `1.mp4` Narrator keeper, which speaks to 7.83s of 8.00s and is
correct. An earlier version of this script rejected it, which is exactly the kind
of confidently-wrong checker this project has been burned by three times.

What it CANNOT judge, and never claims to: whether the words are the right
words, whether the voice matches the character, or whether a second quieter
vocal layer sits underneath. Those stay human. The point is that a take failing
TAIL or LENGTH is objectively wrong and can be re-rolled without asking, while a
take passing all three is *plausible* and goes to the review queue rather than
to the user's attention mid-pass.

Exit code 0 = plausible, 1 = mechanically rejected. Use --json for a report.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"

_spec = importlib.util.spec_from_file_location("sd", ROOT / "work" / "speech_density.py")
sd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sd)

WORDS_PER_SEC = 2.5        # MUST match work/build_audio_pass_durations.py.
                           # Measured from the 14 known-good clips: median 2.75,
                           # range 1.14-3.89. This was 3.5 while the duration
                           # builder used 2.5, so the INVENTED and SILENCE
                           # thresholds were computed against a pace 40% faster
                           # than the one the clips were actually rendered for --
                           # every take looked like it contained more speech than
                           # its words could account for. Fixed 2026-08-18.
LENGTH_SLACK = 0.75        # render may exceed the configured length by this much
INVENTION_RATIO = 1.75     # speech / word-estimate above this is invented
MIN_SPEECH_FRACTION = 0.35 # of the word-estimated duration


def scripted_words(clip_id: str) -> int:
    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    for c in cfg["clips"]:
        if c["id"] != clip_id:
            continue
        n = 0
        for d in c.get("dialogue_timing") or []:
            m = re.search(r"[“\"]([^”\"]*)[”\"]", d["line"])
            if m:
                n += len(re.findall(r"\S+", m.group(1)))
        return n
    return 0


def configured_seconds(clip_id: str) -> float | None:
    """The length this clip is SUPPOSED to be rendered at."""
    f = EQ / "audio_pass_durations.json"
    if not f.is_file():
        return None
    for r in json.loads(f.read_text(encoding="utf8"))["clips"]:
        if r["id"] == clip_id:
            return float(r["audio_pass_seconds"])
    return None


def validate(path: Path, clip_id: str, configured_override: float | None = None) -> dict:
    """Score one take.

    `configured_override` is the length this PARTICULAR attempt was rendered at.
    It matters because of the duration ladder (work/duration_ladder.py): a retry
    is deliberately rendered one rung longer or shorter than the base length in
    audio_pass_durations.json. Without the override, every upward rung would be
    flagged WRONG_LENGTH and the checker would reject its own correct retries —
    the fifth time in this project that a checker measured the wrong thing.
    Pass the rung's `render_seconds` from the manifest.
    """
    a, sr = sd.read_audio(path)
    dur = len(a) / sr
    mask, hop = sd.speech_mask(a, sr)
    spans = sd.runs_from_mask(mask, hop)
    speech = sum(e - s for s, e in spans)
    last_end = spans[-1][1] if spans else 0.0
    tail_quiet = dur - last_end

    words = scripted_words(clip_id)
    expected = words / WORDS_PER_SEC if words else 0.0

    want = configured_override if configured_override is not None else configured_seconds(clip_id)
    faults = []
    if words == 0:
        if speech > 1.5:
            faults.append(f"speech in a non-dialogue clip ({speech:.1f}s)")
    else:
        if want is not None and dur > want + LENGTH_SLACK:
            faults.append(
                f"WRONG_LENGTH: rendered {dur:.2f}s but the configured length is "
                f"{want:.2f}s — {dur-want:.2f}s over. This means the renderer used a "
                f"stale frame count, NOT that the take is bad. If this take was a "
                f"deliberate duration-ladder retry, pass its rung length as "
                f"--configured-seconds; the checker is wrong, not the take. "
                f"Otherwise re-render at the configured length — do not re-roll the seed."
            )
        if expected and speech > expected * INVENTION_RATIO:
            faults.append(
                f"INVENTED: {speech:.1f}s of speech for {words} words "
                f"(~{expected:.1f}s expected) — {speech/expected:.1f}x"
            )
        if expected and speech < expected * MIN_SPEECH_FRACTION:
            faults.append(
                f"SILENCE: only {speech:.1f}s of speech for {words} words "
                f"(~{expected:.1f}s expected)"
            )

    return {
        "clip": clip_id,
        "file": str(path),
        "duration": round(dur, 2),
        "speech_seconds": round(speech, 2),
        "speech_fraction": round(speech / dur, 3) if dur else 0.0,
        "last_speech_ends": round(last_end, 2),
        "quiet_tail": round(tail_quiet, 2),
        "scripted_words": words,
        "expected_speech": round(expected, 2),
        "configured_seconds": want,
        "spans": [(round(s, 2), round(e, 2)) for s, e in spans],
        "faults": faults,
        "verdict": "REJECT" if faults else "plausible",
        "note": ("Mechanically plausible. Words, voice identity, and any second "
                 "vocal layer still require a human listen." if not faults else
                 "Objectively wrong — re-roll without asking."),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--clip", required=True)
    ap.add_argument("--configured-seconds", type=float, default=None,
                    help="length THIS attempt was rendered at; use the ladder rung's "
                         "render_seconds when validating a duration-ladder retry")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"no such file: {p}", file=sys.stderr)
        return 2

    r = validate(p, args.clip, args.configured_seconds)
    if args.json:
        print(json.dumps(r, indent=2))
    else:
        print(f"{r['clip']}  {r['verdict']}")
        print(f"   duration {r['duration']}s | speech {r['speech_seconds']}s "
              f"({r['speech_fraction']:.0%}) | quiet tail {r['quiet_tail']}s")
        print(f"   {r['scripted_words']} scripted words -> ~{r['expected_speech']}s expected")
        for f in r["faults"]:
            print(f"   FAULT {f}")
        print(f"   {r['note']}")
    return 1 if r["faults"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
