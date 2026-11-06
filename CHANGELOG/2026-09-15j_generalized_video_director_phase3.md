# 2026-09-15j - Generalized Video Director Phase 3 live VRAM flip-flop

Wired Wan 2.1 + Qwen2.5-VL Caption V4 through `vram_controller`.
**Not compiled live.** Awaiting architect approval before `--compile`.

- `local_agent/vram_controller.py`
  - `prepare_for_comfyui` unloads Ollama, stops *owned* llama.cpp, refuses if
    an unowned Qwen is already on :11436 (16 GB OOM guard).
  - `release_after_comfyui` always POSTs Comfy `/free` then waits for VRAM
    headroom.
  - `prepare_for_vlm` / `release_after_vlm` for Caption V4 on :11436.
- `local_agent/dspy_orchestrator.py` rewritten; mock flags removed.
  - `generalized_video_metric` clamps floats, then:
    1. `prepare_for_comfyui(reason="Wan 2.1 generation")`
    2. SDXL start/end + Wan FLF with clamped cfg/denoise/steps
    3. `release_after_comfyui(reason="Wan 2.1 complete")` in `finally`
    4. frame extract + Qwen2.5-VL on :11436
    5. `release_after_vlm`
  - `TimeoutError` (hang / dropped queue) returns MIPRO 0.0 + JSON error.
    Does not start ComfyUI. `--compile` still required.
- CPU tests in `test_dspy_orchestrator.py` (injected hardware callables).
  Does not overwrite `temporal_physics_v1.json`.
