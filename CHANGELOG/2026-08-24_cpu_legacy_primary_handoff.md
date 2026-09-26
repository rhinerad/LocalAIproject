# 2026-08-24 — CPU handoff for unavailable primary chats

## What changed

- `local_agent/router.py` now recognizes a persisted compatible Huihui primary
  tag such as `huihui_ai/qwen3-abliterated:14b-v2` even while that optional
  14B model is not installed on the active Ollama tiers.
- It continues that specific primary-model family on the installed
  `huihui_ai/qwen3-abliterated:8b` CPU fallback with `num_gpu=0` and four CPU
  threads. Other unavailable models still refuse rather than silently changing
  the chat.
- Added router regression coverage and documented that the H3
  `qwen3vl_32b_minimax_h3_*` file is a ComfyUI render encoder, not a local chat
  model.

## Why

The current persisted chat was pinned to `14b-v2`, but both live Ollama tiers
only contain the Huihui 8B chat model. The old availability guard returned a
blank CPU route before the documented 14B → 8B resilience rule could run.

## Verification

- Live CPU server exposes `huihui_ai/qwen3-abliterated:8b`.
- The direct route check for the legacy 14B pin returns the dedicated CPU host,
  the Huihui 8B model, `num_gpu=0`, and four threads.
- `python local_agent/test_router_switching.py`: 14/14 passed.

## 32B status correction

The H3 `qwen3vl_32b_minimax_h3_*` file is a render encoder and remains
unloaded until a user-authorized render. That is distinct from the historical
local-agent vision/action model `huihui_ai/qwen3-vl-abliterated:32b`, documented
as successfully pulled on 2026-08-23. Its action-extraction role was explicitly
replaced by the exact Qwen2.5-VL Caption V4 setup on 2026-08-24 because 32B
could CPU-offload. See `2026-08-24_32b_model_history_correction.md`.
No render was started.
