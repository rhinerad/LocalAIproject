# 2026-09-15h — Phase 1 VRAM traffic controller scaffold

## What changed

- Added `local_agent/vram_controller.py`.
- Tracks the current VRAM owner in `local_agent/runtime/vram_owner.json` using an atomic temp-file replace.
- Adds Ollama wrappers that send `keep_alive: 0` for one-shot chat/generate calls.
- Adds `wait_for_ollama_unload()` to poll `/api/ps` before handing VRAM to ComfyUI.
- Adds ComfyUI `/free` helper with an `update_state` flag so `prepare_for_comfyui()` does not accidentally clear its own pending ownership state.
- Adds the local llama.cpp/VLM endpoint constant on port `11436`.

## Notes

- The pasted scaffold contained Markdown-wrapped URLs. This entry saves the intended plain local HTTP URLs so the module is executable.
- This is Phase 1 scaffolding only. It does not yet force every router, ComfyUI, or VLM call through the controller.
- No render, model load, ComfyUI job, PowerInfer work, registry change, or predictor change was started.
