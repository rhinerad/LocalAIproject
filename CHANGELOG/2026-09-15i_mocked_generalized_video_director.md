# 2026-09-15i — Mocked Generalized Video Director Phase 2 scaffold

## What changed

- Added `local_agent/dspy_orchestrator.py`.
- Defines `clamp_director_hparams()` for float CFG, denoise, and steps output.
- Adds `generalized_video_metric()` using mocked, deterministic minimum-axis scoring:
  - alignment
  - temporal coherence
  - aesthetic quality
- Stores mocked JSON feedback on `generalized_video_metric.last_feedback`.
- Adds a five-row in-code Beta Set with one explicit Backrooms row:
  - `GVD-B01`
- Adds a DSPy `GeneralizedVideoDirector` Signature and a MIPROv2 compile entry point.

## Safety / scope

- This is a mocked loop only.
- It does not call ComfyUI.
- It does not call Qwen2.5-VL, llama.cpp, Ollama, or the VRAM controller.
- It does not start a render or load a model.
- The optimizer refuses to run unless the operator explicitly passes `--run`.
