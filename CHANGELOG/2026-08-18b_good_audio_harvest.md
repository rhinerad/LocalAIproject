# 2026-08-18 — harvesting voice references from the good-audio folder

## What changed

New tool `work/harvest_good_audio_masters.py`. It identifies every take in
`ComfyUI-Shared\output\video\good audio\`, measures and removes the leading
'hmpf' burst the operator reported, and cuts a Narrator master.

Outputs:

```
outputs/equal_shares/voices/_good_audio_trimmed/       16 trimmed takes + README
outputs/equal_shares/voices/narrator/omni_master_goodaudio_v1.wav
outputs/equal_shares/good_audio_harvest.json           full machine report
```

## The finding that changes the plan

The operator's expectation was that this folder would supply voice references
"for the characters", plural. **It cannot.**

Every take was identified from the API graph embedded in its own MP4 and matched
to `story_config.json` by dialogue text. All 14 speaking takes matched at 100%
string similarity. The result:

| take | clip | speakers |
|---|---|---|
| `2.mp4` | 00A | Narrator |
| `3-1.mp4` | 00C | Narrator |
| `4_`.mp4` | 00D | Narrator + Male Visitor One |
| `5-.mp4` | 00D2 | Narrator + Male Visitor One + Male Visitor Two |
| `6_.mp4` | 00E | Narrator |
| `7-.mp4` | 00F | Narrator |
| `8-.mp4` | 00G | Narrator |
| `9-.mp4` | 00I | Narrator |
| `10-.mp4` | 00J | Narrator |
| `11.mp4` | 00K | Narrator |
| `12.mp4` | 00L | Narrator |
| `13.mp4` | 00M | Narrator |
| `14.mp4` | 00N | Narrator |
| `15.mp4` | 00O | Narrator |
| `16_dummyclip`, `17.mp4` | — | no dialogue |

**This is the opening narration run, 00A–00O, and it is one voice.** `00B` and
`00H` are absent — that is the skip the operator remembered, and it is two clips,
not one.

The folder can therefore supply **three** voices at most: Narrator, Male Visitor
One, Male Visitor Two. It supplies nothing for Kent, Avery, Doris, Ryann, Faith,
Terminal voice, or the other eleven speakers. **The audition pass is still
required for those**, and the plan to source all character references from this
folder does not work.

## The leading burst — measured, not assumed

**12 of 16** takes open with it. Consistent shape: onset at t = 0.02 s, duration
0.08–0.38 s, peak −11 to −27 dBFS, followed by 0.20–1.20 s of room tone before
the first word. The four without it are `2`, `12`, `13`, `16_dummyclip`.

**A flat one-second cut was rejected.** Trim points range from 0.38 s to 1.60 s.
Cutting 1.0 s everywhere would have removed 0.62 s of real speech from `6_.mp4`
and left 0.60 s of burst in `11.mp4`. Each file is measured and trimmed to 80 ms
before its own first sustained speech run.

This matters more for a reference than for a take: an `<Audio N>` is timbre
conditioning, so a non-speech vocal burst inside it is a characteristic H3 can
learn. This project has already shipped one voice master that turned out to be
road noise.

## Incidental confirmation of the duration ladder

Not looked for, but it fell out of the extraction. The nominal durations the
operator dialled by hand on these good takes:

```
7.0  7.0  8.0  8.0  9.0  9.0  9.0  9.0  9.0  9.0  10.0  10.0  10.0  11.0
```

Whole seconds, clustered around 9, spread outward — the operator was already
walking a duration ladder by hand, on the takes that came out right. Every one
also quantized to a legal 17k+5 frame count, and **every one begins
`subject_definitions:` with nothing above it**, consistent with
`docs/GOLDEN_REFERENCE/README.md`.

## Verified after this change

- 16/16 takes carry a readable embedded graph; all identified.
- 14/14 dialogue matches at 100% similarity, no clip matched twice.
- Narrator master: 10.90 s from `13.mp4` (00M), **74% speech density** per
  `work/speech_density.py` — comfortably over the 6 s reliability target.
- The master is one contiguous passage from one take. Natural pauses are left
  in; nothing is spliced.
- Written as a new versioned sibling. `omni_master_v1.wav` and
  `omni_master_v2.wav` are untouched, as are all source MP4s.

## Still unverified

- **Whether the trimmed heads are actually clean.** The burst is detected by an
  energy heuristic. It has not been heard. The listening sheet asks for filenames
  if any survive.
- **Whether the new Narrator master is better than `omni_master_v2.wav`.** It is
  longer and denser; that is not the same as better, and the operator already
  approves the v2 source. It is offered, not substituted — nothing is rewired
  until `sync_omni_audio_config.py` is pointed at it deliberately.
- **The two visitor candidates are inference, not measurement.** Their lines sit
  inside multi-speaker takes and the scripted `dialogue_timing` cannot locate
  them, because these takes were rendered at speech length rather than scene
  length. Attribution is by dialogue order alone. They are parked in the review
  folder as `unverified_candidate` and are NOT installed as masters. One is
  0.12 s and is probably a fragment rather than a line.

## Graph impact

None. No render was performed and no workflow was modified.

---

# Addendum — persistent memory established, and a real bug found while doing it

## `docs/GOLDEN_REFERENCE/` is now the project's memory

| File | What it is |
|---|---|
| `PROVEN_FACTS.md` | **New.** Everything established, each line with its measurement. Explicitly states that anything absent from it is unproven, including claims made in `CLAUDE.md`. |
| `GOOD_AUDIO_GRAPHS.json` | **New.** The complete API graph from all 16 good takes, plus identification and audio measurements. 186 KB of evidence that does not depend on re-probing or on network access. |

Pointers added at the top of `CLAUDE.md`, `README.md`, `START_LOCAL_AGENT.md`,
and `CHANGELOG/README.md`, so no agent can reach the render path without passing
`PROVEN_FACTS.md` first.

## The settings are now proven across 15 renders, not 1

`GOLDEN_REFERENCE/README.md` previously generalised from `11.mp4` alone. Extracted
from all 16: **every one of the 13 checked fields is identical across all 15
ref2va takes** — UNet, text encoder, both VAEs, sampler, scheduler, steps,
denoise, megapixels, aspect, multiple, fps, bit depth, frame expression,
`ref_image_size`. All 15 read audio from `1.mp4`. All 15 begin
`subject_definitions:`.

`17.mp4` is the sole outlier: **fl2va** (`MiniMaxH3ImageToVideo`), no references,
no dialogue. It is excluded from every invariant claim and that exclusion is
recorded in the JSON itself.

**Reference image count is NOT invariant — 8 takes use one, 7 use two, all sound
clean.** Recorded so nobody "fixes" it.

## A real bug, found by the consistency sweep

`work/validate_audio_take.py` had `WORDS_PER_SEC = 3.5` while
`work/build_audio_pass_durations.py` had been corrected to `2.5`. The validator was
computing its `INVENTED` and `SILENCE` thresholds against a pace **40% faster**
than the one the clips were being rendered for, so every take looked like it held
more speech than its words could account for. Now 2.5 in all three places
(`build_audio_pass_durations.py`, `validate_audio_take.py`,
`build_voice_auditions.py`), verified by grep.

This is the sixth time a checker in this project was measuring the wrong thing.

## The reversed doctrine chased down everywhere it was still asserted

`"H3 fills whatever window it is given with speech"` was live in nine places.
Corrected in all of them, each with the measurement:
`CLAUDE.md`, `START_LOCAL_AGENT.md`, `CHATGPT_START_AUDIO_PASS.md`,
`docs/AUDIO_PASS_RUNBOOK.md`, `docs/H3_PROMPT_RULES.md` §9,
`docs/WORKFLOW_NOTES.md`, `work/build_audio_pass_durations.py`,
`work/pad_accepted_soundtracks.py`, `work/sync_omni_audio_config.py`,
`work/render_audio_pass.py`.

Left alone deliberately: `work/render_audio_pass.BACKUP_before_header_removal.py`
(kept as evidence of the fault) and `work/build_voice_reference_map.py`, whose
`"H3 speaks early and rarely fills the window"` is a *different* claim and is
consistent with the correction.

## Verified after this change

- Every `.py` in `work/` compiles except `generate_equal_shares.py` — see below.
- `WORDS_PER_SEC` is 2.5 in all three files that define it.
- No uncorrected instance of the fill-the-window claim remains; every surviving
  mention sits inside a correction, a strikethrough, or the evidence backup.
- `GOOD_AUDIO_GRAPHS.json` parses and contains all 16 graphs.

## Pre-existing breakage, NOT caused by today's work

`work/generate_equal_shares.py` line 107 has a `SyntaxError: unterminated string
literal` — a nested same-quote `.replace("'",'')` inside an f-string. It was
already broken before this session and was not touched. Flagged, not fixed: it
appears to be a superseded generator and repairing it blind could change
`story_config.json` generation. **Do not run it** until someone establishes
whether it is still in the path.

## Still unverified

Unchanged from the entries above: no render has been made since any of the fixes
of 2026-08-17 or 2026-08-18. The trimmed audio heads have not been heard. The
visitor candidates are inference. Everything today is code, document, and
measurement level.
