# 2026-08-18 — the duration ladder becomes the retry rule

## What changed

The retry knob for bad speech is now the **duration**, not the seed.

Operator instruction, verbatim:

> "when generating audio and trying to get perfect English words (getting rid of
> gibberish or mispronounced words) use this generation pattern. Example start at
> 10 sec; if gen is bad (has mispronounced words) add a second. If that does not
> work go back to 10 and go down to 9 seconds. The pattern of generation to fix
> gibberish and mispronounced words is the following; 10, 11, 9, 12, 8, 13, 7 and
> so forth."

Implemented as one module, `work/duration_ladder.py`, and referenced from
everywhere else. Rungs alternate outward from the base, up first:

```
D    D+1    D-1    D+2    D-2    D+3    D-3    D+4    D-4
```

### Files touched

| File | Change |
|---|---|
| `work/duration_ladder.py` | **New.** The sequence, the bounds, the frame quantization, and a CLI. Single source of truth. |
| `work/render_audio_pass.py` | Retry loop walks the ladder instead of re-rolling. Seed now **held fixed** across a clip's rungs and pinned as `ladder_seed` so a resumed run continues the same ladder. Every attempt records `ladder_rung`, `render_seconds`, `render_frames`. |
| `work/render_audio_pass.py` | `retry_suffix()` gutted — it used to append a `STRICT AUDIO RETRY` paragraph. See "second thing removed" below. |
| `work/validate_audio_take.py` | New `--configured-seconds` override, and the `WRONG_LENGTH` message rewritten. |
| `work/build_voice_auditions.py` | Each pack now ships its own precomputed ladder table alongside the 3 seed takes, with an explicit two-knob rule. |
| `docs/H3_PROMPT_RULES.md` | New §10. §9 given a correction banner and its pace figures fixed. |
| `docs/AUDIO_PASS_RUNBOOK.md` | New step 4a: a symptom→knob table. Duration-split figures corrected. |
| `START_LOCAL_AGENT.md` | Standing-answers table rewritten for retries; the "H3 fills the window" claim corrected. |
| `CLAUDE.md` | Ladder added as the fifth binding audio rule; the fill-the-window claim corrected. |

## Why

The number of words is fixed by the script. The window is fixed by the frame
count. So the speech rate the model must hit is **words ÷ duration**, and the
seed cannot move it. When that rate is one H3 cannot articulate, it does not slow
down or leave a gap — it slurs, elides, or invents syllables to fill the metre.
That is the mechanism by which re-rolling a mispronunciation has been producing a
*different* mispronunciation rather than clean speech. One second is roughly a
10% change in rate.

Up first because a fractionally slow delivery sounds natural and a rushed one
does not.

### A second thing was removed, and it matters more than it looks

`retry_suffix()` used to append a `STRICT AUDIO RETRY` paragraph to attempt 2 and
beyond. It is now gone, for two reasons.

1. It made a retry a different **prompt** as well as a different take, so no
   outcome could be attributed to anything.
2. It is the same class of defect as the 2026-08-17 fault: text added at render
   time to a prompt that `build_native_r2v_prompts.py` generated whole. None of
   the 14 known-good clips carries any wrapper text. `reference_job_prefix()` was
   neutered on 2026-08-17 for exactly this; `retry_suffix()` was the same bug
   still live in the retry path and nobody had looked at it.

The prompt now reaches H3 byte-identical on every attempt, first or fifth.

## Evidence

**For the mechanism:** none beyond the operator's own hand-rendering, and that is
stated plainly in the module docstring. What the 14 good clips do establish is
that duration is a *live* variable that was tuned by hand: they run 7.0 / 9.0 /
9.0 / 10.0 / 10.0 / 11.0 s, none of them a scripted length.

**For the implementation:** verified mechanically, see below.

**For the `retry_suffix` removal:** `docs/GOLDEN_REFERENCE/README.md`, which
records that all 14 good clips begin `subject_definitions:` with nothing above
it, extracted from the workflow embedded in each MP4.

## Verified after this change

- The rung sequence reproduces the operator's example exactly: a base of 10
  yields 10, 11, 9, 12, 8, 13, 7, 14, 6.
- Every rung quantizes to a frame count congruent to 5 modulo 17, all distinct,
  monotone in the intended direction.
- The cap works: `00B`, whose base 14.375 s is already near its scripted 15.0 s,
  gets a purely downward ladder and never proposes an illegal length.
- `--configured-seconds` suppresses `WRONG_LENGTH` on an upward rung and the
  fault still fires without it.
- All four edited Python files parse.
- The 17 audition packs regenerate with correct per-character ladders.

## Still unverified

**No render has been made under this rule.** Everything above is code and
document level.

Specifically not verified:

- that the ladder actually fixes a mispronunciation on this machine
- that holding the seed across rungs behaves as intended — a different frame
  count is a different latent shape, so the rungs are not strictly comparable
  even with the seed pinned, and the module says so
- that removing `retry_suffix()` changes anything, since no retry has run since
- whether the fault the ladder is aimed at is even still present, because the
  header removal and the 124/124 prompt-source fix of 2026-08-17 are themselves
  unrendered

The first real Stage-1 pass settles all of these at once, and every attempt now
carries its `ladder_rung`, so the rule can be judged on which rungs produced
clean takes rather than on anyone's belief about it.

## Graph impact

**None.** The ladder changes only the `length` value fed to the existing graph.
No node, model, sampler, scheduler, or megapixel value differs from
`docs/GOLDEN_REFERENCE/PROVEN_GOOD_AUDIO_GRAPH.api.json`. No diff against the
golden reference was required and none is claimed.
