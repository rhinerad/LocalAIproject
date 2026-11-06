# 2026-09-17c — Backrooms prompt-pack master batch runner

## What changed

- Added `master_batch_runner.py` at the project root.
- The runner processes the exported Backrooms Sitcom prompt-pack clips from:
  `local_agent/runtime/managed_tasks/backrooms_sitcom_pack_20260917/`.
- It launches `generate_video.py` as a separate child process for every clip.
  This intentionally avoids importing the generator so GPU/Comfy/PyTorch memory
  can be released between clips.
- It records completion state in both:
  - `local_agent/runtime/managed_tasks/backrooms_sitcom_pack_20260917/progress.json`
  - each local clip JSON under `clips/C###.json`
- It resolves natural-language frame-handoff notes such as “Use Last Frame of
  C001” to previously recorded output media when available.
- It skips completed clips on resume if the recorded MP4 still exists.

## Verification

- `python -m py_compile master_batch_runner.py`

## Not started

- No render was started.
- No ComfyUI process was touched.
- No model weights, predictors, registry entries, or generated media were
  modified.
