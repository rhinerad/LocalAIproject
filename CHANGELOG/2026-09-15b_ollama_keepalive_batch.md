# 2026-09-15b - Ollama keep_alive=0 and 24-clip Backrooms batch

Scope: unload Ollama immediately after DSPy inject so Wan 2.2 can take
the 16 GB card. Batch runner is opt-in (`--execute`).

## Changed

- `configure_local_dspy_lm`: `keep_alive=0` plus `extra_body={"keep_alive": 0}`.
  Preferred models start with `llama3.2:1b` and `qwen2.5:1.5b`.
- `unload_ollama_model()` POSTs `/api/generate` with `keep_alive=0` after
  compiled inference.
- `backrooms_24_clips.json` + `batch_generate_backrooms.py`.
