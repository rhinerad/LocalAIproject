# Changelog 2026-09-18f — ComfyUI 0.36 + FastH3 + Ref2VA

## Upgrade
- ComfyUI **0.36.0** (`ee71d5c4`) on Rockernow; prior commit recorded in `ASTRA_PRE_UPGRADE_COMMIT.txt`.

## FastH3 Dense — PASS
- FL2VA + FastH3 Dense LoRA + Kitchen attention + MiniMaxH3SigmaShift (12/3) + 6 steps.
- ~271.45 s wall, ~15462 MiB peak → `astra_post36/fasth3_00001_.mp4`.

## Ref2VA Autogrow — PASS (single + dual)
- Correct wiring: `ref_images.ref_image_N` dotted keys; `<Picture i>` in prompt.
- Single: ~300.74 s, peak 15258 MiB → `ref_single_00001_.mp4`
- Dual: ~289.64 s, peak 15418 MiB → `ref_dual_00001_.mp4`
- ImageBatch / bare `ref_images` IMAGE path documented as broken.

## Audit closure
Live GPU checklist from the original Astra audit prompt is complete for continuity, ffmpeg master path, reconcile/faults, VRAM envelopes, attention bench, FastH3, and Ref2VA multi-ref identity lock.
