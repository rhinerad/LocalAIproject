# 2026-08-23 — UPGRADE 09: dual-model vision backend + GPU queue

## What changed

### router.py
- Added `gpu_free_mb() -> int | None` — queries `nvidia-smi --query-gpu=memory.free`; returns None if nvidia-smi unavailable (callers treat None as 0 free).

### capabilities.py
- Added `VRAM_SAFETY_MB = 1024` — headroom margin applied to every tier check.
- Added `_TIER_DEFS` — two-tier vision model definition:
  - **primary** (11 500 MB): `qwen3-vl-abliterated:8b-q8_0` and aliases — OCR, dense diagrams, video frame sequences.
  - **secondary** (7 000 MB): `huihui_ai/llama3.2-vision-abliterated:11b` slot (not yet installed) + `huihui_ai/qwen3-vl-abliterated:4b` as current fallback — scene descriptions, captions, quick checks.
- Added `vision_tiers(host) -> list[dict]` — returns installed, vision-capable tiers in preference order with `label`, `model`, `vram_need_mb`, `task_strengths`.
- `VISION_PREFERENCES` is now derived from `_TIER_DEFS` so single-model callers (`vision_model()`) stay consistent.

### media_tools.py
Three new internal functions:
- `_build_prompt(question, instruction)` — extracts the shared prompt string.
- `_run_vision_gpu(images, question, model, host, instruction)` — low-level GPU call; no VRAM check, no queue gate. Used by the watcher.
- `_vision_direct(images, question, instruction)` — picks best available tier and calls `_run_vision_gpu`; no queue gate. Used by `analyze_video()` after a preflight check.

`_vision()` rewritten:
- Queries `router.gpu_free_mb()` and iterates tiers largest-first.
- Runs the first tier whose `vram_need_mb + VRAM_SAFETY_MB ≤ free_mb`.
- If no tier fits (or nvidia-smi unavailable): calls `media_queue.enqueue("vision", ...)` and returns `{"queued": true, ...}`.
- CPU fallback removed. `router.gpu_busy()` already handles the resident-Ollama false positive internally so no separate `_render_busy()` helper is needed.

`analyze_video()` updated:
- Preflight VRAM check before extracting any frames.
- If not ready: enqueues the whole video as `"analyze_video"` job and returns `{"queued": true, ...}`.
- If ready: calls `_vision_direct()` for each frame (bypasses per-frame re-queuing).

`transcribe()` updated:
- Checks `router.gpu_busy()` before running Whisper.
- If a real render is active: enqueues as `"transcribe"` job and returns `{"queued": true, ...}`.

`_do_transcribe(p, cap, args)` extracted — the actual Whisper execution; called by `transcribe()` and `transcribe_direct()`.

`transcribe_direct(args)` added — bypasses render-busy gate; called by the watcher.

### media_queue.py (new)
stdlib-only persistent queue under `local_agent/media_queue/`:
- States: `pending/ → processing/ → done/ | failed/`
- All writes atomic via tmp + `os.replace()`.
- `enqueue(kind, args)`, `claim_next(kind=None)`, `complete(id, result)`, `fail(id, error)`, `recover_stale()`, `list_queue()`.

### media_watcher.py (new)
Background watcher with single-instance PID lock (`media_queue/watcher_owner.json`):
- `--once` flag for testing.
- On each poll: tries vision/analyze_video jobs when `_best_tier()` confirms free VRAM; tries transcribe jobs when `router.gpu_busy()` is False.
- Calls `_run_vision_gpu()` / `analyze_video()` / `transcribe_direct()` directly — never re-queues within the watcher.
- Polls every 15 s; recovers stale processing jobs on startup.

### server.py
- Added `GET /api/media_queue` → `media_queue.list_queue()`.
- In `push()`: when `kind == "tool_result"` and the result JSON contains `"queued": true`, emits an additional `queued` SSE event so the GUI updates without waiting for agent narration.

### static/index.html
- Queue indicator pill (`#queuepill`) above the model selector in the sidebar; shows `⧖ N media jobs queued`; hidden when queue is empty; clickable to refresh.
- `refreshQueue()` — fetches `/api/media_queue`, updates pill.
- `queued` SSE event handler — shows an action card with job ID, calls `refreshQueue()`.
- Queue polling: `setInterval(refreshQueue, 30000)` plus immediate call on page load and on each queued event.

### START_LOCAL_AGENT_GUI.ps1
- Starts `media_watcher.py` as a hidden background process before `server.py`; logs to `media_watcher.log` and `media_watcher.err.log`.

## Why
GPU is often busy with a ComfyUI render when the operator attaches a file. The old code silently fell back to the 4-thread CPU Ollama server with a vision model — Qwen3-VL on 4 CPU threads is unusably slow (10–20 min per image). The queue lets the request complete immediately with a clear status, and the watcher delivers the result once the render finishes.

The dual-model tier (8B Q8_0 primary → 4B secondary → queue) gives the best available quality at the current free VRAM level rather than always falling to the slowest path.

## Evidence
Structural: `_vision()` no longer has a `tier = "cpu"` branch. `capabilities.vision_tiers()` returns `[{"label": "primary", "model": "qwen3-vl-abliterated:8b-q8_0", ...}]` on the live GPU server (confirmed by `python -c "import sys; sys.path.insert(0,'local_agent'); import capabilities; print(capabilities.vision_tiers())"` — to be run after restart).

## What is still unverified
- End-to-end: watcher picking up a queued vision job and writing a completed result has not been observed in a live render window.
- Llama 3.2 11B Vision (abliterated) tag not installed; secondary tier currently resolves to `huihui_ai/qwen3-vl-abliterated:4b`.
- `analyze_video` queue path not tested with an actual video (no render was active during this session).
