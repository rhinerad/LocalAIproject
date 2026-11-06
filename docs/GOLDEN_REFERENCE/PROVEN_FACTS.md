# PROVEN FACTS — the project's memory of what is actually established

**This file is the answer to "what do we know for certain?"** Every line below is
a measurement taken from a render that exists on this machine, with the command
that produces it. Nothing here is inference, summary, or an agent's recollection.

Anything not in this file is **not** proven, however confidently it is written
elsewhere. Three separate doctrines in this project turned out to be wrong after
being repeated across a dozen documents; the fix was to stop trusting prose and
start extracting graphs.

**Evidence file:** `GOOD_AUDIO_GRAPHS.json` — the complete API graph from all 16
takes, plus their identification and audio measurements.
**Reproduce everything here:** `python work/harvest_good_audio_masters.py`

---

## 1. The settings, proven across 15 renders — not one

Extracted 2026-08-18 from every ref2va take in
`ComfyUI-Shared\output\video\good audio\`. **All 15 agree on every field.** Not
"the docs say"; the graphs are identical.

| Field | Value | Renders agreeing |
|---|---|---|
| `UNETLoader.unet_name` | `minimax_h3_ref2va_pruned_nvfp4.safetensors` | 15/15 |
| `CLIPLoader.clip_name` | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` | 15/15 |
| video VAE | `minimax_h3_video_vae_fp16.safetensors` | 15/15 |
| audio VAE | `minimax_h3_audio_vae_fp32.safetensors` | 15/15 |
| sampler / scheduler | `res_multistep` / `simple` | 15/15 |
| steps / denoise | 20 / 1.0 | 15/15 |
| megapixels | **0.2** | 15/15 |
| aspect / multiple | `16:9 (Widescreen)` / 32 | 15/15 |
| fps / bit depth | 24.0 / 8 | 15/15 |
| frame expression | `max(5, round(a*24)) + (5 - (max(5, round(a*24)) % 17)) % 17` | 15/15 |
| `ref_image_size` | `match` | 15/15 |
| audio reference source | `VHS_LoadVideoPath` on **`1.mp4`**, output 2 | 15/15 |
| prompt first characters | **`subject_definitions:`** | 15/15 |

**The one outlier is `17.mp4`**: fl2va (`MiniMaxH3ImageToVideo`), no reference
sockets. Exclude it from the invariants above — but **it does have dialogue**, it
is clip `01B`, and it is the evidence that the fl2va path works. See §10.

### What is NOT invariant, and therefore is not what makes the audio good

**Reference image count varies: 8 takes use one, 7 use two.** Both produce clean
audio. Do not "fix" a clip because it has the wrong number of images.

---

## 2. What the good-audio folder actually contains

Every take identified from **its own embedded graph**, then matched to
`story_config.json` by dialogue text. All **15** speaking takes matched at 100%
similarity, none matched twice. **Filename order was not trusted and should never
be.**

| take | clip | speakers | duration |
|---|---|---|---|
| `2.mp4` | `00A` | Narrator | 9.417 s |
| `3-1.mp4` | `00C` | Narrator | 7.292 s |
| `4_`.mp4` | `00D` | Narrator + Male Visitor One | 8.000 s |
| `5-.mp4` | `00D2` | Narrator + Male Visitor One + Male Visitor Two | 10.125 s |
| `6_.mp4` | `00E` | Narrator | 8.000 s |
| `7-.mp4` | `00F` | Narrator | 10.125 s |
| `8-.mp4` | `00G` | Narrator | 9.417 s |
| `9-.mp4` | `00I` | Narrator | 9.417 s |
| `10-.mp4` | `00J` | Narrator | 9.417 s |
| `11.mp4` | `00K` | Narrator | 9.417 s |
| `12.mp4` | `00L` | Narrator | 9.417 s |
| `13.mp4` | `00M` | Narrator | 11.542 s |
| `14.mp4` | `00N` | Narrator | 10.125 s |
| `15.mp4` | `00O` | Narrator | 7.292 s |
| `16_dummyclip` | — | no dialogue | 7.292 s |
| **`17.mp4`** | **`01B`** | **Wealthy commuter + Unhoused man — fl2va** | 9.417 s |

### The consequences, which are easy to get wrong

- **It is essentially one voice.** 14 of the 15 speaking takes are the
  **Narrator** — the opening run `00A`–`00O`. The fifteenth is `01B`.
- **`00B` and `00H` are missing.** Two clips, not one.
- **The folder can supply five voices at most** — Narrator, Male Visitor One,
  Male Visitor Two, Wealthy commuter, Unhoused man. Of those, **only Narrator and
  Male Visitor One are recurring and therefore need a master at all** (§10); the
  other three are one-offs that need nothing.
- It contains **no audio whatsoever** for Kent, Avery, Doris, Ryann Sally, Faith
  White, Terminal voice, Volunteer, or Housing representative — **the eight
  recurring characters that still need masters.**
- Therefore **the voice-audition pass is still required** and cannot be skipped by
  harvesting this folder.

*(Corrected 2026-08-18: this section originally said 14 speaking takes and listed
`17.mp4` as having no dialogue. The harvest tool read prompts only from
`PrimitiveStringMultiline` nodes and `17.mp4` carries its prompt inline on the
sampler node, so its two spoken lines were invisible. Tool fixed.)*

---

## 3. Silence does not cause gibberish

The claim *"H3 fills whatever window it is given with speech"* appeared in
`CLAUDE.md`, `START_LOCAL_AGENT.md`, `docs/H3_PROMPT_RULES.md` §9,
`build_audio_pass_durations.py`, and `validate_audio_take.py`. **It is false.**

| take | words | duration | speech | silence | operator's verdict |
|---|---|---|---|---|---|
| `4_`.mp4` | 13 | 8.0 s | 3.5 s | **56%** | clean |
| `15.mp4` | 8 | 7.3 s | 5.4 s | 26% | clean |
| `2.mp4` | 17 | 9.4 s | 7.8 s | 17% | clean |

A take that is more than half silence came out right. The `00B` failures that the
doctrine was built on had **two** faults at once — a prepended header **and** a
long duration — and only the duration was noticed.

**Fitting the render to the line is still correct** (cheaper, one fewer variable,
every good take is short). It is a precaution, not a cause.

---

## 4. Delivered speech pace

Measured across the 14 speaking takes: **median 2.75 words/second, range
1.14–3.89.** The project previously used 3.5 w/s, taken from a single bad `00B`
render, which made every clip too short. `build_audio_pass_durations.py` now uses
2.5, just under the median.

---

## 5. The operator was already walking a duration ladder

Nominal durations dialled by hand on the takes that came out right:

```
7  7  8  8  9  9  9  9  9  9  10  10  10  11
```

Whole seconds, clustered at 9, spreading outward — independent support for the
duration ladder rule (`work/duration_ladder.py`, `H3_PROMPT_RULES` §10). Every one
also quantized to a legal 17k+5 frame count.

**This is corroboration, not proof.** No render has yet been made by walking the
ladder deliberately.

---

## 6. The leading 'hmpf' burst

**12 of 16 takes** open with it. Onset t = 0.02 s, duration 0.08–0.38 s, peak −11
to −27 dBFS, followed by 0.20–1.20 s of room tone before the first word. Clean:
`2`, `12`, `13`, `16_dummyclip`.

**Trim per file, never a flat second.** Trim points span **0.38 s to 1.60 s**. A
flat 1.0 s cut would remove 0.62 s of real speech from `6_.mp4` and leave 0.60 s
of burst in `11.mp4`.

This matters most for `<Audio N>` references, which are timbre conditioning — a
non-speech vocal burst inside one is a characteristic H3 can reproduce.

---

## 7. The two faults that corrupted the 2026-08-17 autopilot pass

Both extracted from render PNGs, both fixed, **both still unrendered**.

1. **A header was prepended to all 124 prompts** (`AUDIO-FIRST REFERENCE JOBS…`),
   declaring `<Picture 1>` and `<Picture 2>` a third time. None of the 15 good
   takes has anything above `subject_definitions:`.
   Fix: `reference_job_prefix()` returns `""`.
2. **46 clips rendered with the pre-native prompt**, because
   `audio_pass_config_omni_v1.json` holds only the 78 dialogue clips and the
   renderer fell back to `story_config["prompt"]`.
   Fix: fallback is now `prompts_native_r2v/<clip>.txt`. 124/124 verified to start
   `subject_definitions:`.

A third of the same kind was found on 2026-08-18: **`retry_suffix()` was appending
a `STRICT AUDIO RETRY` paragraph to every attempt after the first.** Also now
returns `""`.

---

## 8. Standing rule — what "verified" means

> A change to the audio or picture pipeline is not verified until the workflow
> embedded in a real render has been extracted and diffed against
> `PROVEN_GOOD_AUDIO_GRAPH.api.json` or `GOOD_AUDIO_GRAPHS.json`.

Agreement between documents proves nothing. On 2026-08-16 the config matched the
docs, the drift check was clean, and the regenerated prompts looked right — while
the renderer sent a corrupted prompt to all 124 clips.

```bash
ffprobe -v error -show_entries format_tags=prompt -of json <take.mp4>
```

---

## 10. Who actually needs a voice — measured

Operator rule, 2026-08-18: a character who speaks in only one clip needs no voice
master and no `<Audio N>`. Counted from `story_config.json`:

| | count | |
|---|---|---|
| speakers in the film | **18** | |
| recurring, need a master | **10** | Kent 32 clips, Narrator 16, Ryann Sally 14, Avery 10, Doris 5, Faith White 3, Volunteer 3, Housing representative 3, Terminal voice 2, Male Visitor One 2 |
| one-off, need nothing | **8** | Aid worker, Congregation member, Council member, Crew lead, Doris recording, Male Visitor Two, Unhoused man, Wealthy commuter |

Clip routing that follows:

| | count | clips |
|---|---|---|
| fl2va — no recurring speaker, no references | **4** | `01B`, `20B`, `22B`, `30B` |
| ref2va — references for recurring speakers only | **74** | |
| of those, mixed (a one-off speaks too) | **3** | `00D2`, `27E`, `28C` |

Audio reference slots used across the film: **90**. No clip exceeds H3's limit of
three.

### fl2va works, and `17.mp4` is the evidence

`17.mp4` in the good-audio folder **is clip `01B`** — one of the four fl2va
clips. `MiniMaxH3ImageToVideo`, `minimax_h3_fl2va_pruned_int8_convrot`, 0.2 MP,
20 steps, `res_multistep`/`simple`, denoise 1.0, 24 fps, two `LoadImage`
boundaries, a real AAC track. The operator filed it under good audio.

Two caveats stated honestly:

1. Its prompt declares `<Audio 1>` and `<Audio 2>` although the fl2va node **has
   no audio reference sockets**. It promised references the graph could not
   supply and worked anyway. fl2va prompts should drop those declarations rather
   than depend on the model ignoring them — as of 2026-08-18 the generator does.
2. "Filed under good audio" is the operator's judgement of the take as a whole,
   not a verified statement that both one-off voices are right.

### A correction this uncovered

`harvest_good_audio_masters.py` originally read the prompt only from
`PrimitiveStringMultiline` nodes. `17.mp4` carries its prompt inline on the
sampler node instead, so the harvest reported **"17.mp4 — no dialogue"**, which
was wrong. It is `01B` with two spoken lines. Fixed; the count of speaking takes
in the folder is **15, not 14**, and the folder also contains Wealthy commuter
and Unhoused man — both one-offs, so neither needs anything.

### And a live bug it exposed

`build_native_r2v_prompts.py` numbered `<Audio N>` by the speaker's position in
the clip while skipping speakers without a master. Reference tags follow
**connection order**, so a clip whose first speaker had no master declared the
second as `<Audio 2>` and wired it into `ref_audio_0`. Four mis-numbered tags
across `27E`, `28C`, `00D2`. Tags are now assigned sequentially as sockets fill.

---

## 11. Open — measured, and still unresolved

- **Whether the doubled voice is fixed.** The `retention_analysis` fix and the
  header removal are both plausible causes and neither has been rendered since.
- **Video-audio-track vs standalone WAV as the reference.** All 15 good takes
  read audio from `1.mp4` via `VHS_LoadVideoPath`; the autopilot uses `LoadAudio`
  on a WAV. Same socket, different content. Untested.
- **Whether the trimmed heads are clean.** Detected by energy heuristic, not
  heard.
- **Whether the duration ladder fixes a mispronunciation here.** Corroborated by
  §5, not demonstrated.
