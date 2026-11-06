# Upgrade 7 — point it at folders, get renders. The automated ComfyUI maker.

Paste everything below the line into Claude Code. **No downloads.**

---

Build a **generic batch renderer**: the operator points the agent at a job folder
of prompts and reference assets, and it renders the whole sequence through
MiniMax H3 unattended.

```
A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
```

This is **not** Equal Shares. It must never read or write
`outputs/equal_shares/**` state — no touching `audio_pass_manifest.json`,
`story_config.json`, or `voice_requirements.json`. It is a second, general
pipeline that happens to reuse the same proven render infrastructure.

## Read first

- `docs/reference/MINIMAX_PROMPT_GUIDE_ref.md` §2.1–2.5 and §4.1 — the reference
  label and marker rules. **Quoted below where they matter; verify them.**
- `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md` §1 — the settings that must not change
- `work/render_single_pass.py` — `build_ref2va_workflow`, `build_fl2va_workflow`,
  `start_comfy`, `stop_comfy`, `submit_workflow`, `wait_for_completion`. **Reuse
  these. Do not rewrite the render path.**
- `work/thermal_guard.py`, `work/duration_ladder.py`

## THE MOST IMPORTANT THING IN THIS DOCUMENT

**Socket numbers are zero-based. Prompt tags are one-based.** They are not the
same number and confusing them is the single most likely way this ships broken.

| Operator's name | ComfyUI socket | Prompt tag | Role |
|---|---|---|---|
| img 0 | `ref_images.ref_image_0` | **`<Picture 1>`** | character reference |
| img 1 | `ref_images.ref_image_1` | **`<Picture 2>`** | setting — stays the same |
| img 2 | `ref_images.ref_image_2` | **`<Picture 3>`** | second character, when present |
| video ref | first video socket | **`<Video 1>`** | motion only |

Tags follow **connection order**, so if a slot is empty the later tags shift down.
Three images wired means `<Picture 1>`, `<Picture 2>`, `<Picture 3>`. Two images
wired means `<Picture 1>` and `<Picture 2>` — never `<Picture 3>`.

This project already has a scar from exactly this class of bug: a prompt declared
`<Audio 2>` while the reference was wired into `ref_audio_0`, so every voice in
the clip was mis-attributed. Four clips were affected. See
`CHANGELOG/2026-08-18c_one_off_speaker_rule.md`.

**Also: the operator's existing hand-made renders used `<Video 0>`.** That is
non-conforming — the guide is one-based throughout. A tag of `<Video 0>` likely
bound to nothing, which would explain why those prompts needed heavy prose to
compensate. Emit `<Video 1>`.

## Job 1 — verify the video socket before building anything

**Do not assume `MiniMaxH3ReferenceToVideo` accepts a video reference.** The
project's 15 proven-good graphs use image and audio references only; a video
reference socket has never been exercised here.

Establish the truth, in this order:

1. Query the running ComfyUI at `/object_info` for the node's real input schema
2. If a video socket exists, record its exact name
3. If it does not, **stop and report that** — the motion-reference feature cannot
   be built on a socket that is not there, and the operator needs to know rather
   than receive something that silently ignores the video

Write what you find into the CHANGELOG. This is the one genuine unknown.

## Job 2 — the job folder layout

The operator points at one folder. Detect this structure:

```
<job>/
  prompts/       0001.txt, 0002.txt, ...      one per render, sorted
  video_refs/    00.mp4, 01.mp4, ...          motion reference per render
  img0/          character reference
  img1/          setting reference
  img2/          second character (optional)
  renders/       created by you — output goes here
```

**Slot filling rule — auto-detect, do not ask:**

- a slot folder holding **one** file → that file is used for **every** render
- a slot folder holding **numbered** files → matched **sequentially** to the
  prompt index

So `img1/` with a single `setting.png` stays fixed across the whole batch, while
`img0/` with `00.png, 01.png, …` advances per render. That covers both cases the
operator described without any configuration.

Accept flat layouts too — files named `prompt_001.txt`, `video_001.mp4`,
`img0_001.png` in one folder. Sort **naturally**, so `2` comes before `10`.

**Report the plan before rendering anything.** A dry run that prints, per render:
prompt file, video ref, each image slot, resolved tags, duration, output path.
The operator must be able to see the whole batch is correctly paired before a
single frame is generated. Mismatched counts are reported as a warning with the
pairing shown, not silently truncated.

## Job 3 — the motion-only lock, done properly

The operator's rule: **the video reference supplies motion only. The model must
never copy imagery from it.**

The guide has a canonical construction for exactly this. From §2.1:

```text
<Subject 1> is the woman whose appearance comes from <Picture 1> and whose
walking motion comes from <Video 1>.
```

That is the correct way to say it — appearance sourced from the image, motion
sourced from the video, in the subject definition where the model expects it.

And `retention_analysis` gets the matching marker. From §4.1 the visible-content
markers are `fully_preserved`, `partially_preserved`, `attribute_transfer`,
`weak_reference`, and the guide's own example for a structural video reference is:

```text
<Video 1> (cut and pacing structure): weak_reference - ...
```

So emit, for a motion-only video:

```text
<Video 1> (motion and camera structure only): weak_reference - only the movement,
timing, and camera behaviour are taken from <Video 1>. None of its people,
faces, bodies, clothing, setting, or lighting appear in the target video.
```

Plus the identity line pinning appearance to `<Picture 1>`.

**This is stronger than prose alone** because `retention_analysis` is the section
this project already proved the model actually acts on — adding it is what
removed the doubled voice after weeks of prose failing to.

Build all three pieces automatically: the subject definition, the retention line,
and a short confirming sentence in `detailed_description`. The operator's prompt
files should not have to contain any of it.

## Job 4 — the renderer

New `work/batch_render_folder.py`. Reuse the existing infrastructure; do not
reimplement it.

Non-negotiable, from `PROVEN_FACTS.md` §1:

```
ref2va      minimax_h3_ref2va_pruned_nvfp4.safetensors
fl2va       minimax_h3_fl2va_pruned_int8_convrot.safetensors
encoder     qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
VAEs        minimax_h3_video_vae_fp16 + minimax_h3_audio_vae_fp32
sampler     res_multistep / simple, denoise 1.0, 20 steps
fps/depth   24 / 8-bit
frames      congruent to 5 modulo 17
```

Megapixels is a **CLI argument**, defaulting to 0.9 for picture work. Turbo
checkpoints, nodes and LoRAs stay prohibited.

Operational rules, all reusing what exists:

- **one backend per render**, stopped after, `thermal_guard` before and after
- claim `render_queue_owner.json` — never run beside the Equal Shares pass
- resume: skip renders whose output already exists, unless `--force`
- **never overwrite.** Attempt N goes to a new file; nothing is replaced
- per-job manifest inside the job folder, recording for every render: prompt
  file, every reference path, resolved tags, seed, duration, frames, megapixels,
  output path, status
- `--limit N` so the operator can try three before committing to eighty
- on VRAM failure, drop 0.1 MP and record it; floor at 0.4 MP for picture

If a prompt has dialogue, reuse `duration_ladder.py` for retries — same rule,
duration not seed. If it has none, a failed render retries once then reports.

## Job 5 — validate before spending GPU time

Every assembled prompt goes through `local_agent/validate_h3_prompt.py` **before**
it is submitted. A prompt that fails is reported with its faults and **skipped**,
not rendered.

Eighty renders at several minutes each is hours. Catching a malformed prompt
beforehand costs milliseconds.

Note honestly in the CHANGELOG: that validator was written for this project's
six-section dialogue prompts and passes 124/124 of them. Behaviour on
motion-reference prompts is **unproven** — if it produces false positives on
valid batch prompts, fix the validator with a recorded measurement, do not
disable the check.

## Job 6 — expose it to the agent

Two tools in `local_agent/tools.py`:

- **`batch_plan`** — `{"folder": "..."}`. Scans, pairs, resolves tags, validates
  every prompt, returns the plan. **Read-only, renders nothing.**
- **`batch_render`** — proposal only, exactly like `propose_gpu`. Returns the
  command for the operator to approve. **The agent must never start a batch.**

Then the operator can say *"look at D:\jobs\scene12 and tell me if it's ready"*
and get a real answer, followed by a command they run themselves.

## Verify

Build a synthetic job folder with 3 prompts, 3 video refs, a sequential `img0/`,
a single fixed `img1/`, and a two-file `img2/`. Then:

- [ ] pairing is correct and reported before anything renders
- [ ] the fixed slot repeats; the sequential slots advance
- [ ] natural sort puts `2` before `10`
- [ ] tags are **one-based and contiguous**, and match the sockets actually wired
- [ ] a render with only two images emits `<Picture 1>`/`<Picture 2>` and **no**
      `<Picture 3>`
- [ ] the motion lock appears in all three places: subject definition, retention
      line with `weak_reference`, and detailed description
- [ ] mismatched counts warn and show the pairing rather than truncating silently
- [ ] an invalid prompt is skipped with its faults listed, not rendered
- [ ] `--limit 1` renders exactly one
- [ ] re-running skips completed renders; `--force` redoes them
- [ ] nothing under `outputs/equal_shares/**` is read or written — verify by
      timestamp
- [ ] the queue owner is claimed and released
- [ ] `batch_render` refuses to execute and returns a command instead
- [ ] guard rails still refuse; `validate_h3_prompt.py` still **124/124** on the
      Equal Shares set

## Do not stop

Work through. The one legitimate stop is Job 1 finding that no video reference
socket exists — report that clearly and continue building everything else, with
the motion reference disabled and the reason recorded.

Finish with a `CHANGELOG/` entry: the real socket name you found, the tag mapping
as implemented, and whether the validator needed adjusting for this prompt shape.
