# Adaptive Huihui 14B → 8B GPU routing

## Change

- Added the idle-GPU reasoning pair to `local_agent/router.py`:
  `huihui_ai/qwen3-abliterated:14b` is primary and
  `huihui_ai/qwen3-abliterated:8b` is its paired fallback.
- Compatible Ollama `-v2` tags are recognised as the configured models. This
  workstation currently has `14b-v2` and `8b-v2` installed.
- Added predictive routing at more than 16,000 estimated input tokens. The
  estimate includes system text, conversation/tool history, schemas, and tool
  results. The primary is explicitly unloaded before this predictive fallback.
  Primary receives a 20,480 context option; fallback receives 32,768.
- Added reactive failover for Ollama HTTP 5xx/timeout/OOM-like errors. The
  primary is evicted with `keep_alive: 0`, then the exact same turn is retried
  once on the 8B GPU model. It never silently accepts CPU layer offload.
- Routing is recalculated before every tool-hop, so growing native tool-call
  history can switch to 8B without abandoning a multi-step task.
- Retained render priority: if ComfyUI, the render owner, GPU telemetry, or an
  unknown GPU state says busy, the existing CPU route applies and no 14B/8B GPU
  retry is attempted.
- Fixed a live-test edge case: VRAM occupied by a model listed by this Ollama
  server's `/api/ps` is treated as the agent's own residency, not as an external
  render. Unknown high VRAM remains busy. Queue ownership, port 8188, and known
  foreign compute processes still take priority.
- When the GPU is reserved, CPU routing now prefers Huihui 8B over Dolphin.
  The dedicated CPU server cannot see the model because the two Ollama servers
  have separate model stores; its attempted local registration was blocked by
  the machine's network policy before any bytes transferred. Until that store
  is shared, the route uses the already-installed 8B via the GPU Ollama service
  with `num_gpu: 0` and the existing four-thread cap. This is CPU-only
  inference—not GPU layer offload—and never loads weights onto a render GPU.
- Corrected configured-tag eviction so `:14b` unloads a resident `:14b-v2`
  model before either predictive or reactive fallback.
- Added revision marker `2026-08-22-adaptive-14b-8b-r6` to `/api/status`. The desktop launcher detects an old
  local-agent process on loopback port 8760, replaces only that stale instance,
  and starts the current code.

## Verification

- `python local_agent/test_router_switching.py` — 9/9 passed, including short
  primary context, >16k predictive fallback, and OOM eviction/retry.
- `python local_agent/test_native_tool_calling.py` — 9/9 passed, including
  reactive primary-OOM retry plus all existing tool, guard-rail, legacy, stop,
  attachment, and persistence coverage.
- `python local_agent/test_general_assistant.py` — passed.
- `python local_agent/test_media_analysis.py` — 6/6 passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
  — 124/124 valid.
- Live router inspection while the pipeline was stopped: GPU idle, 162 MB used,
  no foreign compute process; it selected
  `huihui_ai/qwen3-abliterated:14b-v2` after the model pull completed.
- Live primary inference returned `PRIMARY_OK` from 14B v2. A 21,096-token
  live request selected `huihui_ai/qwen3-abliterated:8b-v2` with reason
  `predictive context-length protection` and returned successfully. No CPU tier
  or ComfyUI/render process was involved.

No render, ComfyUI backend, media pipeline, download command, or project
evidence was started, modified, moved, renamed, or deleted by this change.
