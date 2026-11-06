# 2026-09-21a — live still + LTX VRAM profiles

Used the existing Rockernow Comfy on :8188 (queue empty, Qwen :11436 down,
batch owner released). Did not start a second backend.

## Still (generate_still)

- Graph: `known_good_still.api.json` RealVisXL 512², 1 step.
- After `/free` baseline 532 MiB; peak used 7510 MiB; extra **6978 MiB**.
- Output: `gvd_tool_router/known_good_00001_.png`
- Prompt `9f06efd4-9ab1-4a2d-835e-8bf1dbb52ae6`
- Promoted `known_good_sdxl_txt2img_v1` with evidence=local.

## LTX 2.3 distilled (execute_fast_action)

- Graph: GGUF `LTX-2.3-distilled-Q3_K_S.gguf`, Gemma 12B FP4 on CPU,
  distilled LoRA 384, 480×256, 9 frames, 8 steps euler cfg 1.0.
- After `/free` baseline 534 MiB; peak used **15114 MiB**; extra **14580 MiB**.
- Wall ~18 min. Outputs `gvd_tool_router/ltx23_smoke_00001_.png` … frames.
- Prompt `6b6e448f-0345-4bcf-a3dc-3385a8cc9ae7`
- Promoted `ltx23_unvalidated` with that local profile.

## Admission note

Design headroom is 2048 MiB. LTX extra 14580 + 2048 exceeds remaining free
on this 16303 MiB card after a clean `/free`. The profile is recorded as
measured; the router may still return `RESOURCE_BLOCKED` for LTX under the
2048 MiB policy. Still (6978 + 2048) fits.

After both smokes, `/free` returned the card to ~514 MiB used.

## Not measured this pass

IPAdapter identity, Wan continuation, montage (AnimateDiff missing).
