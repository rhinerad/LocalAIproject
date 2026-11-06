# Claude Code — stitch the opening keepers with RVC audio. Paste below the line.

---

Working directory:

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

Read `docs/WORKFLOW_NOTES.md` first. Do not read state from the parent folder's `outputs`.

## Goal

Build a review cut of the accepted opening clips in `A:\Users\rhine\ComfyUI-Shared\output\video\`, with the new RVC-converted voice on the dialogue, so the user can judge how the sequence plays and how the cloned Narrator sounds in context.

**Build two files** so the voice can be compared honestly:

- `OPENING_REVIEW_rvc.mp4` — Kokoro dialogue, RVC-converted where a model exists
- `OPENING_REVIEW_h3.mp4` — the original H3 audio exactly as rendered

Same picture, same cut, same length. Only the audio differs. Put both in `outputs/equal_shares/review/`.

## Bandwidth

Phone hotspot. **Download nothing.** Everything needed is on disk.

## What the videos are

Derived from the workflow embedded in each ComfyUI PNG, matched by timestamp **and** duration:

| File | Duration | Story clip | Anchors |
|---|---|---|---|
| `1.mp4` | 8.00 s | **`00A`** — the film's opening line | narrator_close → 00_v2 |
| `2.mp4` | 15.08 s | **`00B`** | narrator_close → 00_v2 |
| `3.mp4` | 8.00 s | `00C` | 00_v2 → entry_start |
| `4.mp4` | 12.25 s | `00D` | entry_start → 01_v2 |
| `5.mp4` | 10.12 s | `00D2` | 01_v2 → 02_v2 |
| `6.mp4` | 8.00 s | `00E` | 02_v2 → 03_v2 |
| `7.mp4` | 15.08 s | seated close | 03_v2 → seated_close |
| `9.mp4` | 15.08 s | standing close | 03_v2 → standing_close |
| `10.mp4` | 12.25 s | `00I` Narrator reveal | 03_v2 → 04_v2 |
| `8.mp4` | 10.55 s | the `00E` beat — **hosted MiniMax, 1920×1080, 30 fps** | — |

**Verify this yourself** with `work/analyze_takes.py` rather than trusting the table. If your mapping differs, use yours and say so.

`1.mp4` and `2.mp4` share an anchor pair but are **different shots**. `1.mp4` carries the film's first line, "In a world with total equality…" (`00A`); `2.mp4` carries "If all people feel that someone without should be helped…" (`00B`). Include both.

### `8.mp4` — include it, and it drives the output format

`8.mp4` was generated on hosted MiniMax rather than the local H3 install, which is why it is 1920×1080, 30 fps, 48 kHz with a Clipchamp encoder tag. It shows the `00E` beat: the seated man looking up, the standing man looking down. **It is a real clip and belongs in the cut.**

Its faces are legible in a way the 736×416 local renders never are. That contrast is worth preserving rather than flattening, so:

**Build the cut at 1920×1080, 24 fps.** Upscale the 736×416 clips with lanczos; conform `8.mp4` from 30 fps to 24 fps. Do not downscale `8.mp4` to match the others — that would destroy the one thing it demonstrates. The local clips will look soft by comparison. That is accurate and useful information, not a defect in your work.

**`6.mp4` and `8.mp4` cover the same beat** (`00E`, `02_v2 → 03_v2`). Place `8.mp4` immediately after `6.mp4` so the two versions of the same moment play back to back at their real quality. Note this in the manifest so the user can see it was deliberate.

### Cut order

**1 → 2 → 3 → 4 → 5 → 6 → 8 → 7 → 9 → 10**. Roughly 115 s.

Hard cuts, no transitions, no crossfades. This is a review cut, not a grade.

## Audio — the part that matters

### Which characters have a voice model

Only **Narrator** is trained: `narrator_equal_shares_100e.pth` in the Applio logs.

Every other speaker in these clips — Male Visitor One, Male Visitor Two — has **no** RVC model and stays on their plain Kokoro voice. Do not attempt to convert them. That contrast is useful: the user will hear cloned Narrator against un-cloned visitors in the same cut.

### Building the RVC track

For each clip in the cut:

1. Read that clip's `dialogue_timing` from `story_config.json` for speakers and in-clip offsets.
2. Take the matching per-line WAV from `outputs/equal_shares/audio/dialogue/`.
3. If the speaker is the Narrator, convert it with the trained model — same settings as the working conversion: rmvpe pitch, contentvec embedder. Write to `audio/dialogue/<name>_rvc.wav`; **do not overwrite the Kokoro original**.
4. Otherwise use the Kokoro line unchanged.
5. Place each line at its in-clip offset within that clip's slot in the cut.

Only `00A_01_Narrator_rvc.wav` exists so far. You will need to convert the remaining Narrator lines for `00B`, `00C`, `00D`, `00D2`, `00E`, and whichever lines belong to the seated/standing/reveal clips. Derive the list from `audio/dialogue_manifest.json`; do not guess filenames.

**Check every conversion stays within ±0.15 s of its input.** Report any that do not and leave those on Kokoro rather than shipping a drifted line.

### Score

Lay `EQUAL_SHARES_CONTINUOUS_SCORE.wav` under both cuts from its start, at the assembly's own levels: score −25 dB, ducked −8 dB under dialogue. Match `assemble_story.py` so this sounds like the real film, not a rough mix.

The H3 version keeps its native audio and gets the same score treatment, so the only variable between the two files is the dialogue source.

## Output

```
outputs/equal_shares/review/
    OPENING_REVIEW_rvc.mp4        Kokoro + RVC Narrator
    OPENING_REVIEW_h3.mp4         original H3 audio
    OPENING_REVIEW_rvc_alt.mp4    optional: same cut without 8.mp4, if the
                                  resolution jump is too distracting to watch
    OPENING_REVIEW_manifest.json  order, source file, story clip, duration,
                                  per-line voice source and conversion delta
```

Encode **1920×1080, H.264, 24 fps, AAC**. The local clips are upscaled to fit the frame;
their native resolution is unchanged and nothing is re-rendered.

## Report

- your video-to-clip mapping and whether it matched the table
- which Narrator lines were converted, and the duration delta on each
- any line left on Kokoro because conversion drifted, with the number
- total runtime of the cut
- how `8.mp4` conformed from 30 fps to 24 fps, and whether the quality gap against the
  736×416 clips is as stark in motion as it is in stills

Then stop. The user watches and decides whether to train the remaining characters.

## Append to the notes

Add to the RVC section of `docs/WORKFLOW_NOTES.md`: how many Narrator lines converted cleanly, the delta range across a real batch rather than one file, and anything about mixing converted and unconverted voices in the same cut. Append; do not rewrite earlier entries.

## Rules

- **Do not render any video clip.** This is edit and audio work only.
- Do not overwrite any Kokoro line, any raw clip, or `EQUAL_SHARES_DIALOGUE_TIMELINE.wav`.
- Do not modify `story_config.json`, `manifest.json` or `visual_audit.json`.
- Upscaling for the review frame is expected and only affects the review file. Do not
  reframe, crop, or alter aspect. Never write a scaled version back over a source clip.
- These review cuts are not the film. Do not touch `EQUAL_SHARES_FINAL_1344x768.mp4` or the completion audit.
