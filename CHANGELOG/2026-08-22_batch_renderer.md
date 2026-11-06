# 2026-08-22 — Generic batch renderer

**Files added / changed:**

| File | Change |
|---|---|
| `work/batch_render_folder.py` | new — batch render supervisor |
| `local_agent/tools.py` | added `batch_plan` and `batch_render` tools + schemas |
| `tests/batch_test_job/` | new — synthetic verification job folder |
| `CHANGELOG/2026-08-22_batch_renderer.md` | this file |

---

## Job 1 — Video socket truth

**Source consulted:** `ComfyUI-Installs/Rockernow/ComfyUI/comfy_extras/nodes_minimax_h3.py`
(ComfyUI was not running; the node definition was read directly from source.)

**Verdict: The video socket EXISTS.**

```
Autogrow socket name:  ref_videos
Per-slot key prefix:   ref_video_
First slot key:        ref_video_0   (zero-based)
Input type:            io.Image.Input  (a batch of video frames, not a video file)
Maximum slots:         3
```

**Core loading pipeline (no custom nodes required):**

```
LoadVideo  (file in ComfyUI input dir)
  -> GetVideoComponents  (output 0 = IMAGE tensor of frames)
  -> ref_videos.ref_video_0
```

**Tag mapping (socket zero-based, prompt tag one-based):**

| ComfyUI socket | Prompt tag |
|---|---|
| `ref_images.ref_image_0` | `<Picture 1>` |
| `ref_images.ref_image_1` | `<Picture 2>` |
| `ref_images.ref_image_2` | `<Picture 3>` |
| `ref_videos.ref_video_0` | `<Video 1>` |

Operator's existing hand-rendered prompts used `<Video 0>`. That tag is non-conforming
— the guide is one-based throughout. The batch renderer emits `<Video 1>`.

**Presentation order** (from node source — determines tag numbering):
1. All `ref_images` in slot order → `<Picture 1>`, `<Picture 2>`, ...
2. For each `ref_videos` slot: if paired audio → `<Audio j>` then `<Video k>`
3. All standalone `ref_audios` → `<Audio j>`

The batch renderer does not wire paired audio on video slots (motion-only rule).
So for a typical batch render with 2 images and 1 video ref: `<Picture 1>`, `<Picture 2>`, `<Video 1>`.

---

## Motion-only lock — three injections

The operator writes a complete six-section H3 prompt with `<Picture N>` tags only.
The renderer auto-injects `<Video 1>` in all three required places:

**1. `subject_definitions` — standalone `<Video N>` entry (appended):**
```
<Video 1> provides motion and camera pacing reference for this clip; no visual content
from it is reproduced in the target video.
```

**2. `retention_analysis` — `weak_reference` line (appended):**
```
<Video 1> (motion and camera structure only): weak_reference - only the movement,
timing, and camera behaviour are taken from <Video 1>. None of its people, faces,
bodies, clothing, setting, or lighting appear in the target video.
```

**3. `detailed_description` — confirming sentence (prepended before [Shot 1]):**
```
The motion and camera timing of the clip follow the rhythm of <Video 1>, but none of
<Video 1>'s people, faces, clothing, setting, or lighting appear; character appearance
is determined entirely by the reference images.
```

---

## Validator behaviour on batch prompts

`local_agent/validate_h3_prompt.py` was **not modified**.

Measured: the validator passes batch motion-reference prompts (no `<d>` blocks)
without false positives. Relevant checks:
- E06/E07/E08/E17 (dialogue rules) — trivially pass when no `<d>` blocks present
- E10/E11 (Picture tag contiguity and declaration) — work correctly for `<Picture N>` tags
- W04 (empty soundscape on dialogue clip) — not triggered without dialogue
- W05 (no mouth-close clause) — warning only; not an error

The renderer adds an explicit `expect_audio=0` when calling the validator since batch
renders have no audio conditioning sockets wired.

An additional check — `PICTURE_MISMATCH` — is performed after validation: it counts
declared `<Picture N>` in `subject_definitions` and verifies they match the number of
actually-wired image sockets. This is outside the validator because it requires
knowledge of the wiring, not just the text.

Equal Shares set: **124/124 valid** — unchanged by this work. Verified by running
`python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`.

---

## Verification checklist

All items verified by running the plan + tool tests on the synthetic job at
`tests/batch_test_job/` (3 prompts, 3 video refs, sequential img0/, fixed img1/, 2-file img2/).

- [x] Pairing correct and reported before any render (--plan exit 0)
- [x] Fixed slot (img1/setting.png) repeats across all 3 renders
- [x] Sequential slot (img0/) advances: 00.png → 01.png → 02.png
- [x] Natural sort: 2 < 10 (verified with [10,2,1,20,9] → [1,2,9,10,20])
- [x] Tags one-based and contiguous: render 3 (no img2) → `<Picture 1> <Picture 2>` only
- [x] Motion lock in all 3 places: subject_definitions, retention_analysis, detailed_description
- [x] Mismatched img2 count warns with pairing shown, render 3 proceeds with 2 images
- [x] Invalid prompt (Picture count mismatch) returns PICTURE_MISMATCH error
- [x] batch_render returns `{requires_operator_approval: true, command: ...}` — never executes
- [x] Equal Shares state files untouched: audio_pass_manifest.json last modified 6017 min ago
- [x] 124/124 Equal Shares prompts still valid after validator run

Items NOT verified in this session (require real GPU):
- --limit N stops after N renders
- Re-running skips completed renders; --force redoes them
- VRAM drop logic (0.9 → 0.8 → ... → 0.4 MP)
- Queue owner claimed and released during live render

---

## Queue isolation

The batch renderer reads `outputs/equal_shares/runtime/render_queue_owner.json`
(read-only) to detect a live Equal Shares pass, and refuses to start if one is found.
It writes its own lock to `batch_render_queue_owner.json` at the project root.

The batch renderer's ComfyUI runtime directories are inside the job folder
(`<job>/batch_runtime/`), keeping output entirely separate from Equal Shares.
