#!/usr/bin/env python3
"""Compute a SHORTER render length for each Stage-1 soundtrack clip.

THE PROBLEM
-----------
!! CORRECTED 2026-08-18 — the reasoning below is wrong, the output is still right.
!!
!! This docstring claimed "H3 fills the clip", built on the 00B renders. That is
!! NOT supported: `4_`.mp4` in the good-audio set is 56% silence and the operator
!! says it is clean, and `15.mp4` runs at 1.14 w/s and is clean. The 00B failures
!! carried a prepended AUDIO-FIRST REFERENCE JOBS header AND a long duration; the
!! duration was blamed and the header went unnoticed for a week.
!!
!! Fitting the render to the spoken line is STILL CORRECT — it is ~30% cheaper,
!! it removes a variable, and all 14 known-good takes are short. It is a
!! precaution, not a cure. The retry knob for gibberish and mispronunciation is
!! the duration ladder in work/duration_ladder.py.
!! See docs/GOLDEN_REFERENCE/PROVEN_FACTS.md section 3.

Measured on `00B` across three renders, the scripted 30-word line is delivered by
about 10.4 s and then the model produces fresh speech all the way to the final
frame at 14.93 s of a 15.08 s clip.

Three prompt-side fixes failed to stop it:

  1. one `<d>` block per line, no split seams
  2. delivery before the tag, mouth closed immediately after it
  3. an explicit "every voice stops, no extra words are invented" instruction,
     plus removing an ambiguous "one vocal layer at any moment" sentence

None worked, because this is not a wording problem. H3 generates audio jointly
with video across the whole latent and was trained on clips whose soundtrack runs
end to end. Asking it to synthesise six seconds of silence is fighting the model.

Measured across the film: **72 of 78 dialogue clips allot 3 s or more beyond what
their lines take to say.** `00A` over-allots by 9.6 s, `00O` by 9.2 s. The
scripted durations were written for picture and pacing, not for speech length.

THE FIX
-------
Do not ask for silence. Render only as long as the speech needs, and pad silence
in post, where it is exact and free.

  Stage 1 (soundtrack)  render the short length computed here
  Assembly              pad the accepted WAV with digital silence to the
                        scripted duration

The film's 1266 s timeline is untouched: picture still runs its full scripted
length, and the WAV is padded to match. Silence added in an editor is perfectly
silent, which is the one thing a generative model cannot promise.

It is also cheaper. `00B` drops from 362 to 260 frames, about 28% less compute,
and the same saving applies across the pass.

FRAME MATHS
-----------
H3 snaps duration to a 17-frame block grid at 24 fps: the frame count must be
congruent to 5 modulo 17. Every length here obeys that.

PACE
----
3.5 words/second, measured from the 00B renders. Deliberately the *fast* end of
the observed range: over-estimating pace would clip the tail off a real line,
which is far worse than leaving a small margin. TAIL_MARGIN adds that margin.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
OUT = EQ / "audio_pass_durations.json"

WORDS_PER_SEC = 2.5     # measured from the 14 known-good clips: median 2.75,
                        # range 1.14-3.89. 2.5 sits just under the median so a
                        # slow delivery is never truncated. The previous 3.5 was
                        # taken from one bad 00B render and made every clip too
                        # short.
LEAD_IN = 0.6           # settle before the first word
GAP_BETWEEN_LINES = 0.5 # breath between consecutive lines
TAIL_MARGIN = 1.5       # slack so a slower delivery is never cut off
MIN_SECONDS = 3.0       # never render shorter than this


def quote_of(line: str) -> str:
    m = re.search(r"[“\"]([^”\"]*)[”\"]", line)
    return m.group(1).strip() if m else ""


def frames_for(seconds: float) -> int:
    """Round up to the next frame count congruent to 5 modulo 17, at 24 fps."""
    base = max(5, round(seconds * 24))
    return base + (5 - (base % 17)) % 17


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="also write the short lengths into audio_pass_config.json")
    args = ap.parse_args()

    cfg = json.loads((EQ / "story_config.json").read_text(encoding="utf8"))
    rows, saved_frames = [], 0

    for clip in cfg["clips"]:
        timing = clip.get("dialogue_timing") or []
        scripted = float(clip.get("duration") or 0)
        scripted_frames = int(clip.get("frames") or frames_for(scripted))

        if not timing:
            # No speech at all. Nothing to harvest, so nothing to shorten here --
            # these clips are picture-only and are not part of the voice pass.
            rows.append({
                "id": clip["id"], "has_dialogue": False,
                "scripted_seconds": scripted, "scripted_frames": scripted_frames,
                "audio_pass_seconds": scripted, "audio_pass_frames": scripted_frames,
                "pad_silence_seconds": 0.0, "reason": "no dialogue; not in the voice pass",
            })
            continue

        words = sum(len(re.findall(r"\S+", quote_of(d["line"]))) for d in timing)
        speech = words / WORDS_PER_SEC
        need = LEAD_IN + speech + GAP_BETWEEN_LINES * (len(timing) - 1) + TAIL_MARGIN
        need = max(MIN_SECONDS, need)

        # never render longer than the script asks for
        target = min(need, scripted)
        frames = min(frames_for(target), scripted_frames)
        secs = frames / 24.0
        pad = round(scripted - secs, 3)

        saved_frames += scripted_frames - frames
        rows.append({
            "id": clip["id"], "has_dialogue": True,
            "lines": len(timing), "words": words,
            "estimated_speech_seconds": round(speech, 2),
            "scripted_seconds": scripted, "scripted_frames": scripted_frames,
            "audio_pass_seconds": round(secs, 3), "audio_pass_frames": frames,
            "pad_silence_seconds": max(0.0, pad),
            "reason": ("shortened to fit the spoken line; silence padded at assembly"
                       if frames < scripted_frames else
                       "already tight; no shortening possible"),
        })

    dlg = [r for r in rows if r["has_dialogue"]]
    shortened = [r for r in dlg if r["audio_pass_frames"] < r["scripted_frames"]]

    print(f"{'clip':6}{'words':>6}{'script':>8}{'audio':>8}{'pad':>7}  frames")
    for r in sorted(dlg, key=lambda x: -x["pad_silence_seconds"])[:12]:
        print(f'{r["id"]:6}{r["words"]:6d}{r["scripted_seconds"]:8.0f}'
              f'{r["audio_pass_seconds"]:8.2f}{r["pad_silence_seconds"]:7.2f}  '
              f'{r["scripted_frames"]} -> {r["audio_pass_frames"]}')
    print("   ...")
    for r in sorted(dlg, key=lambda x: x["pad_silence_seconds"])[:3]:
        print(f'{r["id"]:6}{r["words"]:6d}{r["scripted_seconds"]:8.0f}'
              f'{r["audio_pass_seconds"]:8.2f}{r["pad_silence_seconds"]:7.2f}  '
              f'{r["scripted_frames"]} -> {r["audio_pass_frames"]}')

    print(f"\ndialogue clips            : {len(dlg)}")
    print(f"shortened                 : {len(shortened)}")
    print(f"frames saved across pass  : {saved_frames}  "
          f"({saved_frames / max(1, sum(r['scripted_frames'] for r in dlg)):.0%} less compute)")

    payload = {
        "purpose": "Stage-1 soundtrack render lengths, shortened to fit the spoken line",
        "why": ("Render only as long as the speech needs and pad silence at assembly, "
                "where it is exact. All 14 known-good takes are short this way, and it "
                "costs ~30% fewer frames. CORRECTED 2026-08-18: this is a precaution and "
                "a cost saving, NOT a cure for gibberish -- 4_`.mp4 is 56% silence and is "
                "clean, so 'H3 fills the clip' is unsupported. The retry knob for bad "
                "words is the duration ladder. See GOLDEN_REFERENCE/PROVEN_FACTS.md s3."),
        "pace_words_per_second": WORDS_PER_SEC,
        "lead_in_seconds": LEAD_IN,
        "gap_between_lines_seconds": GAP_BETWEEN_LINES,
        "tail_margin_seconds": TAIL_MARGIN,
        "frame_rule": "congruent to 5 modulo 17 at 24 fps",
        "assembly_note": ("Pad each accepted WAV with digital silence to "
                          "scripted_seconds. The 1266 s timeline is unchanged; picture "
                          "still runs the full scripted length."),
        "clips": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf8")
    print(f"wrote {OUT}")

    if args.apply:
        cfgp = EQ / "audio_pass_config.json"
        if cfgp.exists():
            apc = json.loads(cfgp.read_text(encoding="utf8"))
            by_id = {r["id"]: r for r in rows}
            n = 0
            for e in apc.get("clips", []):
                r = by_id.get(e["id"])
                if r and r["has_dialogue"]:
                    e["scripted_duration"] = r["scripted_seconds"]
                    e["scripted_frames"] = r["scripted_frames"]
                    e["duration"] = r["audio_pass_seconds"]
                    e["frames"] = r["audio_pass_frames"]
                    e["pad_silence_seconds"] = r["pad_silence_seconds"]
                    n += 1
            apc["duration_policy"] = (
                "Stage-1 render lengths are shortened to fit the spoken line; pad each "
                "accepted WAV with digital silence to scripted_duration at assembly.")
            cfgp.write_text(json.dumps(apc, indent=2), encoding="utf8")
            print(f"updated audio_pass_config.json for {n} clips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
