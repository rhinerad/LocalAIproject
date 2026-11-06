# 2026-09-23f — Refine-checkpoint denoise tuned live: REFINE_DENOISE 0.30 → 0.15

This is the first live run of the refine checkpoint from 2026-09-23e.
It ran FLUX only (stills-only); MiniMax was not used.

## Backend

- The operator asked me to start Rockernow.
- Before starting, nothing listened on 8188 and there was no ComfyUI process.
  The only Python processes were two `practice-score` uvicorn servers on
  :8000. The GPU was idle at 31 °C.
- Started through the sanctioned path,
  `.grok\long-running-background-tasks\restart_comfy_rockernow.ps1`. It logged
  "no listener on 8188" and spawned `start_comfy_rockernow.bat`, so only one
  listener exists.
- `/system_stats` answered after 183 s: ComfyUI 0.36.0, RTX 5080. The queue
  was empty.
- **Rockernow was left running.**

## Upscale-node question from 23e, now closed

- `/object_info` confirms `LoadImage`, `ImageScale`, `VAEEncode`,
  `ImageSharpen`, `KSampler`, `EmptyFlux2LatentImage` and `UltimateSDUpscale`.
- `UpscaleModelLoader` lists all 10 models from
  `ComfyUI-Shared\models\upscale_models` (4x-UltraSharp, RealESRGAN_x2plus, …).
  They reach Rockernow through the Desktop extra-model-paths config.

## The run

- C012 has never been rendered: `progress.json` has C001–C008 only, and C009
  is interrupted. The requested C012→C013 pair was therefore impossible.
- I used the latest real consecutive pair instead: **C008's actual last
  frame, refined with C009's batch prompts**.
  - Both clips are camera mode A, and shadow v3 says chain.
  - Prompts come from `apply_pipeline_rules`, rules v2026-09-18.v1,
    env `apartment_tripod`.
- Tool: `scripts/refine_denoise_compare.py`.
- Source frame:
  `local_agent/runtime/gvd_backrooms_batch/chain_frames/gvd_br_c008_4f1bb60c4c_00001__6ee934a38d_last.png`
- Outputs: `ComfyUI-Shared\output\dspy_opt\dspy_opt_gvd_refine_tune_c009_d{10,15,20,35}_*.png`
- Reports: `refine_tuning/C009_20260923T212627.json` (0.20, 0.35) and
  `C009_20260923T213140.json` (0.10, 0.15).
- Payload dump `debug_refine_tune_c009_d20_payload.json` confirms the refine
  wiring actually submitted:
  - node 5 absent
  - `3.latent_image=["1005",0]`, `3.denoise=0.2`
  - `1005 VAEEncode ← 1004 ImageScale ← 1003 LoadImage`
  - Saved from node 8
  - KSampler: 20 steps, cfg 5.5, seed 0
- Peak FLUX VRAM was 14.8 GB. The GPU peaked at 67 °C, under the 82 °C
  emergency ceiling.

| denoise | face MAD vs src | body MAD | frame MAD | face edge var (src 1126) | mean RGB (src 77.7/84.6/57.9) |
|---|---|---|---|---|---|
| 0.10 | 7.5 | 8.4 | 3.1 | 1121 | 79.1/85.5/57.2 |
| 0.15 | 9.5 | 10.9 | 3.8 | 1116 | 79.8/86.1/57.7 |
| 0.20 | 11.4 | 14.1 | 4.6 | 1124 | 80.6/86.6/58.3 |
| 0.35 | 17.9 | 22.2 | 7.2 | 1165 | 83.2/88.0/60.1 |

Face-crop montage: `refine_tuning/C009_face_ladder.png`.

## What I saw, at native resolution on the face crop

- **At every value:** pose, blocking, tripod, camera position, room, and
  lighting layout are preserved.
- **0.35:** a different, younger, clean-shaven face and tidier hair. Rejected;
  it is a fresh generation wearing the old pose.
- **0.20:** the face is already smoothed and de-aged, with stubble fading.
  The T-shirt print text and the camcorder brand text are regenerated
  (different glyphs).
- **0.10–0.15:** reads as the same person, with stubble, mouth shape, and hair
  mass kept.
- **No value measurably sharpened the face.** Edge variance is flat. The
  ~12% rise in whole-frame edges is grain and texture.
- Every value warms the image a little (R +1.4 to +5.5), so the refine adds
  colour drift instead of removing it.

## Decision

`REFINE_DENOISE = 0.15`. It is the highest value that kept identity at face
scale, and it leaves some headroom for resetting drift. The
`--refine-denoise` help no longer says "untuned".

55/55 tests pass (`test_batch_run_backrooms_continuity`,
`test_batch_run_backrooms_gvd`).

## Side finding

`C001_first_frame.png` (in `refine_tuning/`) shows a different actor from
C008:

- C001: a teenager with short straight hair and a grey tee, in a blue bedroom
- C008: a curly-haired adult, in a bare pale room

That is the current `--continuity off` behaviour, a fresh independent FLUX
still per clip. Identity has already been lost by clip 8. So even a refine
that cleans little is far better for continuity than a `fresh_still` reset.

## Still unverified

- The source frame is first-generation. It has plain codec softness but no
  accumulated chain drift, so whether 0.15 actually *reverses* drift is
  unmeasured. Repeat on the last frame of a 4-deep chain after the small live
  test.
- The refine has only been checked in stills-only mode. No MiniMax clip has
  been rendered from a refined frame. The render-level check in 23e step 2
  (`ffprobe` embedded workflow) is still to do.
- Prompt-only conditioning has no identity anchor: this path has no LoRA or
  IP-Adapter. That is the likely reason higher denoise pulls the face toward
  FLUX's generic reading of the prompt.
