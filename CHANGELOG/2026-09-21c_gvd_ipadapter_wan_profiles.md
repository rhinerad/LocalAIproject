# 2026-09-21c — live IPAdapter identity + Wan I2V profiles

Used the existing Rockernow Comfy on :8188. Did not start a second backend.
Qwen :11436 stayed down.

## IPAdapter (`execute_narrative_scene`)

- Graph: RealVisXL + `IPAdapterUnifiedLoader` PLUS FACE + CLIP-ViT-H, 512², 4 steps.
- Identity ref: `gvd_identity_ref.png` (the measured still).
- CLIP-ViT-H was already on disk as `clip_vision_h.safetensors`; a hardlink
  named `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` was added so UnifiedLoader
  can find it. IPAdapter weights were junctioned into Rockernow `models/ipadapter`.
- Baseline 535 MiB; peak used 9175 MiB; extra **8640 MiB**. Fits 2048 MiB headroom.
- Prompt `7b2b785d-4bb0-4e65-8a2e-5f0398409785`
- Promoted `ipadapter_sdxl_plus_face_unvalidated`.

## Wan 2.2 I2V (`execute_continuous_take`)

- Graph: high-noise Q4 GGUF, UMT5 fp16, Wan 2.1 VAE, start image, 480×256, 5 frames, 4 steps euler.
- Baseline 1303 MiB (residual after IPAdapter `/free`); peak used 12501 MiB; extra **11198 MiB**.
- ~12.5 min. Prompt `3d92f5a1-10e2-4045-a337-4fd491414e84`
- Promoted `wan22_i2v_q4_high_unvalidated`.
- 11198 + 2048 headroom still fits a clean ~15 GB free card. This is high-noise-only,
  not the dual MoE pair.

## Active registry now

| Tool | Implementation | peak extra MiB | 2048 headroom |
| --- | --- | ---: | --- |
| generate_still | known_good_sdxl_txt2img_v1 | 6978 | fits |
| execute_narrative_scene | ipadapter_sdxl_plus_face_unvalidated | 8640 | fits |
| execute_continuous_take | wan22_i2v_q4_high_unvalidated | 11198 | fits |
| execute_fast_action | ltx23_unvalidated | 14580 | tight / may RESOURCE_BLOCKED |

Montage/morph still has no AnimateDiff/Fizz nodes.
