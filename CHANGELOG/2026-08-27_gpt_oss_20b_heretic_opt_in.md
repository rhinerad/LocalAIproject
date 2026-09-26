# 2026-08-27 — opt-in `gpt-oss-20b-heretic` new-chat model

## What changed

- Added `local_agent/setup_gpt_oss_20b_heretic.py`.
  - It targets only `bartowski/p-e-w_gpt-oss-20b-heretic-GGUF` and the exact
    `p-e-w_gpt-oss-20b-heretic-Q4_K_M.gguf` source file.
  - It verifies the published SHA-256 before import, renames the verified file
    to `gpt-oss-20b-heretic.Q4_K_M.gguf`, writes a Modelfile with `num_ctx 8192`,
    and, with `--create`, imports `gpt-oss-20b-heretic` to the private GPU Ollama
    host `127.0.0.1:11434`.
  - It is never invoked by the normal launcher and does not preload the model.
- Added a visible but disabled **gpt-oss-20b-heretic (opt-in, GPU only)** entry
  to the new-chat picker until the exact local Ollama model is installed.
- Made Heretic a strict GPU-only, pinned-chat route. It uses 8,192 context,
  requests the existing GPU gateway approval before loading, and refuses while
  the GPU is busy. It never CPU-offloads and never silently changes to Huihui 8B.
- Updated `README.md` and `OPERATING_MEMORY.md` with this narrow exception to
  the normal abliterated model pair.

## Verification

- `python local_agent/test_router_switching.py`
- `python local_agent/setup_gpt_oss_20b_heretic.py --help`

These are source-level checks only. The model was not downloaded, imported,
loaded, or live-tested in this change.
