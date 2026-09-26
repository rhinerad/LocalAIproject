# 2026-08-27 — Preserve the primary 14B model in the picker

The Qwen3 14B primary model was never removed. A busy GPU at local-agent
startup could leave the GPU model catalogue uncached, and the picker then
omitted GPU-only entries entirely. `router.chat_models()` now always retains
the configured Huihui Qwen3 14B entry. When GPU presence cannot be freshly
verified, it is shown as disabled with **GPU currently unavailable** rather
than incorrectly looking removed. Once the GPU is released, a fresh inventory
makes the same entry selectable again.

The opt-in gpt-oss entry is unchanged.

## Verification

`python local_agent/test_router_switching.py` — 26 passed, including the
busy-start/empty-GPU-catalogue picker regression.
