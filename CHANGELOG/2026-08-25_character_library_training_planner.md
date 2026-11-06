# 2026-08-25 — Consent-gated character library and LoRA training planner

## What changed

- Added `work/character_library.py`.
- `plan` reads a chosen photo directory and returns an inspectable SDXL LoRA
  training proposal: photo count, recommended settings, target LoRA filename,
  and warnings. It has no subprocess, model-load, download, GPU, or write path.
- `register` creates `outputs/stories/character_library.json` only when invoked
  with the explicit `--confirm-consenting-adult` flag.
- Stored character entries retain only a source photo filename, never an absolute
  personal photo path. Duplicate names, invalid image inputs, and non-safetensors
  LoRA filenames are refused.

## Safety boundary

- This is planning/registration scaffolding only. It does not invoke kohya_ss or
  begin training. A real training run remains a separate GPU action requiring an
  explicit adult-likeness confirmation and a fresh operator approval.
- No identity-model download was performed. InstantID/IPAdapter/PuLID remains
  deferred until the operator selects and approves that distinct feature path.

## Verification

- `python work/test_character_library.py` — 4/4 passed.
- `python work/character_library.py --help` — verified both guarded commands.
