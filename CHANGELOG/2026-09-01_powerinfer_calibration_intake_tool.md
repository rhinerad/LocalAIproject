# 2026-09-01 — PowerInfer calibration intake tool

## Added

- `validate_powerinfer_calibration` is a general local-agent tool for an
  operator-supplied `.jsonl` path inside this repository.
- It runs only the existing strict approval/schema validator and returns a
  structured result. It rejects missing, external, oversized, and unapproved
  inputs clearly.
- It is a CPU-only read operation. It cannot render, start ComfyUI/PowerInfer,
  load a model, edit weights, build predictors, benchmark, serve, or change a
  registry.

## Routing correction

`agent.py` now explicitly instructs the model to use this intake tool for a
PowerInfer/calibration JSON request and never to use batch-render tools for it.

## Verification

- `python local_agent\\test_native_tool_calling.py` — 48 tests passed.
- `python local_agent\\test_agentic_state.py` — 12 tests passed.

No GPU workload, model/predictor/weight change, renderer, ComfyUI process,
registry change, or router-setting change was started.
