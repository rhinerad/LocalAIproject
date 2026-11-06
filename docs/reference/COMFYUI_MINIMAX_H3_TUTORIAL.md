# MiniMax H3 in ComfyUI: T2V, I2V, and R2V Video Workflows

**Verbatim copy of <https://docs.comfy.org/tutorials/video/minimax/minimax-h3>,
captured 2026-08-16.** Saved locally so the pipeline does not depend on network
access or on a page that may change. Sections irrelevant to this project
(download cards, Comfy Cloud links) are trimmed; every prompting and settings
statement is intact.

For what this project concluded from it, see `docs/OFFICIAL_H3_DOCS_FINDINGS.md`.
For the rules actually in force, see `docs/H3_PROMPT_RULES.md`.

---

MiniMax H3 is MiniMax's general-purpose, omni-modal generation model, now
available as open weights. It jointly understands text, images, video, and audio
in a single context, and generates video with **native stereo audio**: voice,
sound effects, and music are modeled together in a single forward pass instead of
being layered on afterward. Output is up to 2K resolution, 24fps, and about 15
seconds.

Three example workflows ship in the template library, one per generation mode:

* **Text-to-Video (T2V)**
* **Image-to-Video (I2V)** — with optional first/last-frame control
* **Reference-to-Video (R2V)** — lock in a character, style, motion, camera move,
  or voice from reference images, videos, and audio

These are examples, not an exhaustive list. The model supports more modes through
the native nodes: first/last-frame image-to-video (fl2va) via
`MiniMaxH3ImageToVideo`, and reference-driven generation with images, videos and
audio (ref2va) via `MiniMaxH3ReferenceToVideo`.

## Key features

* **Native stereo audio** — dialogue, sound effects and music generated together
  with the video, synced in one MP4
* **Multimodal context** — text, images, video and audio references combined in
  one generation
* **Reference-driven generation** — lock a character's identity, a style, a
  motion, a camera move, or a voice
* **Instruction following** — describe the relationship between references and
  the target shot in natural language
* **Accurate text rendering** — spelled-out text and brand elements render cleanly
* **Open weights**

## Setting the output resolution

Each workflow uses a **Resolution Selector** node. It computes `width` and
`height` from three settings, and its outputs connect directly to the `width` and
`height` inputs of the MiniMax H3 node:

* **Aspect ratio** — `16:9 (Widescreen)`, `9:16 (Portrait Widescreen)`,
  `1:1 (Square)`, etc.
* **Megapixels** — target total pixel count. Higher gives larger frames; lower
  runs faster
* **Multiple** — the computed resolution is rounded to the nearest multiple of
  this number. **Keep it at `32`** to match H3's resolution grid

> The template ships with a fast preview size. For full-quality output, raise
> Megapixels to about **`1.0` at 16:9**, which yields roughly **1344×768**: H3's
> native canvas, a 768px short edge capped at 768×1344 pixels.

*Project note: this project runs 0.9 MP, deliberately just under native, because
1.0 MP was measured breaking camera control on clip 11. See
`docs/H3_PROMPT_RULES.md`.*

## Models

| Mode | Diffusion model |
|---|---|
| T2V / I2V | `minimax_h3_fl2va_pruned_int8_convrot.safetensors` |
| **R2V** | `minimax_h3_ref2va_pruned_int8_convrot.safetensors` |

Shared by all modes:

```
models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
models/vae/minimax_h3_video_vae_fp16.safetensors
models/vae/minimax_h3_audio_vae_fp32.safetensors
```

*Project note: this install runs `minimax_h3_ref2va_pruned_nvfp4`, a more
aggressively quantised variant than the `int8_convrot` the docs name. Untested
against int8, and a multi-GB download.*

## Prompting tips — T2V

1. **Describe the whole scene**: state the overall scene first (location,
   character, what is happening), then break it into timed shots
2. **Shots, camera, and audio**: describe the shots, camera moves, and the
   accompanying audio (dialogue, SFX, music) in one prompt block
3. **Resolution**: H3's native canvas is a 768px short edge, capped at 768×1344
   and rounded to a multiple of 32
4. **Duration**: the duration input snaps to the model's **17-frame-per-block
   (17k+5) grid at 24fps**
5. **First/last frame**: connect images to `first_frame` and/or `last_frame` on
   `MiniMaxH3ImageToVideo` to turn this into first/last-frame image-to-video

## Prompting tips — I2V

1. **Keyframes**: `first_frame` and `last_frame` are optional; the model
   generates the motion between them
2. **Prompt**: describe the shots, motion, and accompanying audio in one block
3. **Resolution**: as above
4. **Duration**: snaps to the 17k+5 grid at 24fps

## Prompting tips — R2V  *(the mode this project uses)*

1. **Reference by tag**: reference each input by tag **in the exact order it was
   connected**, for example `<Picture 1>`, `<Video 1>`, `<Audio 1>`
2. **Assign each reference a job**: state which reference drives which part of
   the shot (identity, style, motion, camera, voice). **Explicit assignments tend
   to work much better**
3. **Limits**: up to **9 reference images, 3 reference videos** (each can carry
   its own soundtrack), and **3 standalone reference audio clips**
4. **`ref_image_size`**: `match` scales references down to the generation
   resolution for speed; **`max` keeps up to a 2048px short edge for stronger
   identity fidelity** at the cost of speed
5. **Note**: R2V uses the `ref2va` diffusion model, a different set of weights
   from the `fl2va` model used by T2V and I2V

## Official prompt writing guides

MiniMax publishes two, both saved alongside this file:

| Guide | Modes | Local copy |
|---|---|---|
| base | T2VA, I2VA, FL2VA, L2VA | `MINIMAX_PROMPT_GUIDE_base.md` |
| **full-reference** | **R2V** | `MINIMAX_PROMPT_GUIDE_ref.md` |

The reference guide covers the rewrite output structure — subject definitions,
reference labels, and **retention analysis** — and how to assign each reference a
role in the target shot. MiniMax also publishes installable H3 skills at
<https://github.com/MiniMax-AI/MiniMax-H3/tree/main/skills>, including a
prompt-writing skill that packages these guides for agent use.

## Speeding up generation with Sage Attention

Roughly doubles generation speed with minimal quality loss. Optional dependency:

1. Install the `sageattention` package — download the wheel matching your PyTorch
   and CUDA versions from the SageAttention releases page, then
   `pip install <wheel-file>`
2. Install the KJNodes custom nodes, which provide `Patch Sage Attention KJ`
3. Add that node between `UNETLoader` and `BasicGuider`: its `model` input takes
   the model from `UNETLoader`, its `model` output feeds `BasicGuider`. Set
   `sage_attention` to `auto`
4. Only the guider needs the patch; the scheduler generates sigmas and can stay

**Expected console noise:** Sage Attention requires float16 or bfloat16 tensors.
H3 runs some layers in other dtypes, so you may see *"Input tensors must be in
dtype of torch.float16 or torch.bfloat16, using pytorch attention instead"*.
**These messages are expected** — the affected layers fall back to standard
attention and generation still works. Do not debug them.

Alternatively launch ComfyUI with `--use-sage-attention` instead of adding the
node.
