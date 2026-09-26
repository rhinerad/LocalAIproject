# 2026-09-14aa — Media prompt router and bucket resolver

## What changed

- Added `local_agent/media_buckets.py` with a reusable latent bucket resolver
  for SDXL/FLUX-style dimensions. It supports standard aspect strings and
  custom numeric ratios, uses a 1024x1024 pixel budget for 1.0 MP, and snaps
  width/height to a configurable multiple.
- Added `local_agent/prompt_router.py` with target-specific prompt formatting
  for SDXL, FLUX, and video targets.
- Added `tests/test_media_pipeline.py` covering bucket outputs and SDXL/FLUX
  prompt dialect behavior.
- Updated `TODO.md` to mark Media Generation Pipeline Tasks 1 and 4 complete.

## Verification

- `python -m py_compile local_agent\media_buckets.py local_agent\prompt_router.py tests\test_media_pipeline.py`
- `python -m unittest tests.test_media_pipeline -q` — 7 tests, OK

## Safety

- No ComfyUI process, render, model load, predictor change, runtime queue, or
  existing media evidence was touched.
