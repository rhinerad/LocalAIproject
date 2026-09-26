# 2026-09-01 — RealPro V3 Flux UNet profile

## Added

- Registered the operator-provided `realProV3_realProV3Unet.safetensors` as
  the explicit `realpro_flux` profile for the guarded general still-image
  renderer.
- The profile uses `UNETLoader`, Flux `clip_l.safetensors`,
  `t5xxl_fp16.safetensors`, `ae.safetensors`, and `CLIPTextEncodeFlux`.
  It is separate from the existing complete RealVisXL SDXL checkpoint path.
- Added `text_encoders/` and an in-place Downloads model path to the renderer's
  private ComfyUI model-path configuration. The 11.9 GB supplied UNet is not
  moved, overwritten, or treated as an SD 1.5 checkpoint.
- Exposed the `model_profile` choice (`realvisxl` or `realpro_flux`) to the
  local-agent still-image planning and rendering tools.

## Why

The supplied safetensors header contains Flux block names such as
`double_blocks.*.img_attn` and no SD 1.5/SDXL diffusion-model keys. It must use
Flux encoders and VAE; attempting to load it through `CheckpointLoaderSimple`
as SD 1.5 would be invalid.

## Verified

- Header-only inspection: 780 tensors, Flux structure confirmed; no weights
  loaded.
- Static graph/unit tests: `40 tests, OK` across image graph, plan, and render
  guard tests.

## Not yet verified

No RealPro image was generated. A temporary ComfyUI catalogue check did not
reach port 8188 within the short bounded window, so its live catalogue and
first GPU render remain pending. The temporary validation processes were
stopped; no model load or image output was left running.

## AliceMix correction

The operator-provided `realAlicemixV1_v10.safetensors` was inspected before
adding it. It is a 3.1 GB complete **SD 1.5 checkpoint** (text encoder, VAE,
and diffusion-model weights), not a LoRA and not compatible with RealVisXL's
SDXL checkpoint as an attachment. It is now the separate `alicemix_sd15`
profile, with its documented base settings: 768×1024, 30 steps, DPM++ 2M
Karras, CFG 11, and its detailed-light/RAW prompt prefix.

The exact `realesrgan-x4minus` model and the three named negative embeddings
are not installed. The profile therefore does not fake those assets or silently
replace them. It remains a base-pass profile until the exact requested assets
are available and separately validated.
