# 2026-08-17 (later) — pace corrected from the golden set, and a correction to my own doctrine

## What changed

- `work/build_audio_pass_durations.py`: `WORDS_PER_SEC` **3.5 -> 2.5**,
  `TAIL_MARGIN` 1.2 -> 1.5. Durations regenerated; omni config resynced.
- **New** `work/build_voice_auditions.py` and 17 audition packs on the Desktop at
  `EQUAL_SHARES_VOICE_AUDITIONS\`.

## Why — and a doctrine I got wrong

Measured the speaking pace of all 14 known-good clips by extracting the `<d>`
word count and the duration from each MP4's embedded workflow:

```
median 2.75 w/s    mean 2.60    range 1.14 - 3.89
the calculator was assuming 3.50
```

3.5 came from one bad `00B` render. It made every clip too short.

**More importantly, the golden set contradicts `H3_PROMPT_RULES.md` section 9.**
That section says H3 fills unallotted time with invented speech, and I used it to
justify tight fitting. But:

```
15.mp4    8 words in 7.3s   -> 5.4s speech, 74% fill   GOOD
4_`.mp4  13 words in 8.0s   -> 3.5s speech, 44% fill   GOOD
2.mp4    17 words in 9.4s   -> 6.0s speech, 1.61s quiet tail   GOOD
```

`4_`.mp4` is **56% silence** and the operator says it is clean. A clip that is
more than half silence disproves "the model fills silence with gibberish."

The `00B` failures had **two** faults at once — the prepended header *and* a long
duration. I attributed the gibberish to duration and wrote a rule around it. The
golden set says the header was doing the damage. Duration slack is tolerated
fine.

**Section 9 is therefore downgraded from a cause to a precaution.** Fitting the
duration is still sensible; it is not the mechanism.

## The evidence

`ffprobe -show_entries format_tags=prompt` on each of the 14 good MP4s, plus
`work/speech_density.py` on the three slackest.

## Verified after

```
durations rebuilt : 78 dialogue clips, 45 shortened (was 75)
omni config       : 74 render lengths updated, 0 drift after
audition packs    : 17 characters, 51 renders
audition prompts  : all start subject_definitions:, none has <Audio>, one <d> each
```

## Still unverified

- **No render since any of today's fixes.** Prompt-level only.
- Whether removing the header alone fixes the doubling. Untested.
- Whether 2.5 w/s is right. It is derived from 14 clips, not measured on a new
  render.
