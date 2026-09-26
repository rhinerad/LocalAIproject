# GOLDEN REFERENCE — the graph that actually produces good audio

**READ THIS BEFORE CHANGING ANYTHING THAT TOUCHES A RENDER.**

This folder is not documentation. It is the **ground truth**, extracted from
renders that came out correct, and every claim in it is a measurement — not an
inference, not a summary, not something an agent believed.

---

## The rule that created this folder

On 2026-08-17 the operator said, correctly:

> "I asked if you understood all the new information and if it was being used
> correctly in handoff folder so that autopilot does everything correctly, you
> said yes. But you hallucinated."

That happened because "verified" had meant *the documents and the config agree
with each other*. It had never once meant *the graph the renderer actually sent
matches the graph that produced good audio*.

**So the standing rule for this project is now:**

> A change to the audio or picture pipeline is not "verified" until the workflow
> embedded in a real render has been extracted and diffed against
> `PROVEN_GOOD_AUDIO_GRAPH.api.json`. Agreement between documents proves nothing.

ComfyUI embeds the complete API graph in every output PNG **and in every MP4**
(`ffprobe -show_entries format_tags=prompt`). There is never an excuse for
guessing what was sent.

---

## Files in this folder

| File | What it is |
|---|---|
| **`PROVEN_FACTS.md`** | **Start here.** Everything this project knows for certain, each line with its measurement. Anything not in it is not proven. |
| `GOOD_AUDIO_GRAPHS.json` | The complete API graph from **all 16** good-audio takes, plus identification and audio measurements. Machine-readable evidence. |
| `PROVEN_GOOD_AUDIO_GRAPH.api.json` | One graph (`11.mp4`) kept as the canonical single-file diff target. |
| `README.md` | This file — the rule, and the faults found. |

Regenerate the evidence with `python work/harvest_good_audio_masters.py`.

---

## The proven configuration

Originally taken from `11.mp4` alone. **Since 2026-08-18 it is confirmed across
all 15 ref2va takes in the folder — every field below is identical in all 15.**
The one non-conforming file, `17.mp4`, is fl2va with no dialogue and no
references; exclude it from any invariant claim.

| | Value |
|---|---|
| UNet | `minimax_h3_ref2va_pruned_nvfp4.safetensors` |
| Node | `MiniMaxH3ReferenceToVideo` |
| Megapixels | **0.2**, 16:9 (Widescreen), multiple 32 |
| Steps / sampler | 20, `res_multistep` / `simple`, denoise 1.0 |
| fps / depth | 24 / 8-bit |
| Frame expression | `max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17` |
| Duration | **9.0 s** for a 22-word line — short, fitted to the speech |
| `ref_image_size` | `match` |
| Image reference | `ref_images.ref_image_0` ← `LoadImage` |
| Audio reference | `ref_audios.ref_audio_0` ← `VHS_LoadVideoPath` **output 2** on `1.mp4` |
| Prompt | **starts with `subject_definitions:` — nothing before it** |

Measured across **all 15** ref2va takes, 2026-08-18:

- nominal durations **7 7 8 8 9 9 9 9 9 9 10 10 10 11** — all short, all fitted,
  all whole seconds clustered around 9 and spreading outward
- **15/15** begin `subject_definitions:` with nothing above it
- **15/15** take their voice reference from `1.mp4` via `VHS_LoadVideoPath`
- image references vary — **8 use one, 7 use two, all sound clean. So image count
  is not what makes the audio good** — do not "fix" that.

**And the contents are not what anyone assumed.** All 14 speaking takes are the
**Narrator**; this is the opening run `00A`–`00O` with `00B` and `00H` missing.
The folder supplies three voices at most and nothing for the other fifteen
characters. See `PROVEN_FACTS.md` §2 before planning around it.

---

## What the autopilot did differently — verified, 2026-08-17

Extracted from `ComfyUI_00387.png` (clip `11B`) and `ComfyUI_00382.png` (`30A`).

### Fault 1 — a header was prepended to every prompt

```
AUDIO-FIRST REFERENCE JOBS
<Picture 1> is the exact opening composition. Begin on it precisely.
<Picture 2> is the exact closing composition...
Follow the exact timed action and quoted speech below.

subject_definitions:          <- the real prompt started here
```

`<Picture 1>` and `<Picture 2>` are already declared in `subject_definitions`
and again in `retention_analysis`. The prefix made it **three copies**. None of
the 14 good clips has it.

Source: `work/render_audio_pass.py`, function `reference_job_prefix()`.
**Now returns `""` and carries a docstring forbidding its return.**

### Fault 2 — 46 clips rendered with the pre-native prompt

`audio_pass_config_omni_v1.json` holds **78 entries, not 124** — only the
dialogue clips. For the 46 silent ones the renderer found no `prompt_file` and
fell back to `story_config["prompt"]`, the old format with no
`retention_analysis` at all.

Proof: `30A`'s embedded prompt began `One continuous unbroken take. / CAMERA /
REFERENCES`, not `subject_definitions:`.

**Now fixed:** the renderer falls back to `prompts_native_r2v/<clip>.txt`, never
to `story_config`. Verified: **124/124 prompts now start `subject_definitions:`.**

### Measurements of the bad output

| clip | scripted words | speech | verdict |
|---|---|---|---|
| `29B` | 2 | 3.0 s | **5.2× what the words allow** |
| `29C` | 0 | 8.0 s | speech in a silent clip |
| `30A` | 0 | 7.3 s | speech in a silent clip |
| `30C` | 0 | 7.0 s | speech in a silent clip |

*Caveat stated honestly: `work/speech_density.py` cannot distinguish speech from
crowd ambience, and scenes 29–30 may legitimately carry background voices. The
5.2× on `29B` is solid. The three silent clips need an ear before being called
broken.*

---

## Difference NOT yet explained

The good clips take their voice reference from **a video's audio track**
(`VHS_LoadVideoPath` → output 2 on `1.mp4`). The autopilot uses a **standalone
WAV** (`LoadAudio` on `omni_master_v3_*.wav`).

Both land on the same socket, `ref_audios.ref_audio_0`, so functionally the
wiring matches. But the *content* differs: `1.mp4` is the full 8-second `00A`
keeper; the master is a trimmed cut. **This is an untested variable.** If
doubling survives the two fixes above, test this next — do not assume it is
irrelevant just because the socket is the same.

---

## How to verify a change, every time

```bash
# what did the render ACTUALLY receive?
ffprobe -v error -show_entries format_tags=prompt -of json <take.mp4>

# or from the PNG
python work/analyze_takes.py          # reads the embedded API graph
python work/validate_audio_take.py <take> --clip <ID>
```

Then diff against `PROVEN_GOOD_AUDIO_GRAPH.api.json`. If a field differs and you
cannot say why, that is the bug — not something to explain away.
