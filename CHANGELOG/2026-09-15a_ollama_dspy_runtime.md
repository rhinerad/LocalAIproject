# 2026-09-15a - Local Ollama DSPy temporal-physics inference

Scope: run the baked `temporal_physics_v1.json` module through Ollama on
:11434. Silent regex fallback if Ollama/dspy is down. No ComfyUI submit
in the new test script.

## Changed

- `configure_local_dspy_lm` / `ping_ollama` in `local_agent/temporal_physics.py`.
  Prefers `qwen2.5:7b` then `mistral:latest`, else first non-embed model
  (this host has `llama3.1:8b`). `DSPY_DISABLE_OLLAMA=1` keeps CPU tests
  on the deterministic injector.
- `test_dynamic_dspy_dispatch.py` pings 11434, runs compiled CoT, logs
  source/model/timing.
- TODO.md: full offline loop (compiled DSPy + Ollama + txt2img + Wan FLF)
  marked operational.

## Validation

```
python -m unittest tests.test_media_pipeline -q
python test_dynamic_dspy_dispatch.py
```

33 CPU tests passed. Live Ollama run: `source=compiled model=ollama_chat/llama3.1:8b seconds=45.19`
(this host has no `qwen2.5:7b` / `mistral:latest`; picker used `llama3.1:8b`).
