# 2026-08-25 — GPU routing fix: GPU Ollama server down (Case B)

## Diagnostic

Four checks ran against the live agent to identify why chat was routing to CPU 8B
instead of GPU 14B. Results:

```
=== PORT 8188 ===
listening: False                       ← not ComfyUI

=== GPU MEMORY ===
used_mb: 73                            ← well below VRAM_BUSY_MB=2500
free_mb: 15905
compute_procs: [brave.exe, brave.exe, llama-server.exe]   ← all browser/Ollama

=== GPU OLLAMA SERVER :11434 ===
up: False                              ← TRUE CAUSE
tags: []
14b present: False

=== decide() ===
tier: cpu
model: huihui_ai/qwen3-abliterated:8b
gpu_busy: False
reason: CPU requested; using Huihui 8B on the dedicated CPU server (num_gpu=0, 4 threads).
        GPU idle (73 MB used, no foreign compute process)
```

### Four cases eliminated

| Case | Signal | Status |
|------|--------|--------|
| A — render queue owner file | `queue_owner()` = no file | Clear |
| B — GPU Ollama server down | `router.up('127.0.0.1:11434')` = False | **TRUE CAUSE** |
| C — VRAM above threshold | 73 MB used, threshold 2500 MB | Clear |
| D — ComfyUI on port 8188 | listening = False | Clear |

Root cause: the GPU Ollama server (:11434) was not running. The routing logic itself
is correct — `decide()` falls to CPU when `up(GPU_HOST)` is False because there is
no server to select the 14B from. This is safe-fail behaviour, not a routing bug.

## Changes

### `START_LOCAL_AGENT_GUI.ps1`

- Added `$StartupGpuModel` variable (reads `$env:EQUAL_SHARES_PRIMARY_REASONING_MODEL`,
  defaults to `huihui_ai/qwen3-abliterated:14b`).
- Added `Ensure-GpuChatModel([string]$Model)` function — mirrors `Ensure-CpuChatModel`
  but targets the GPU server at `127.0.0.1:11434`:
  - Checks `/api/tags` via `Get-ServerModels` for the configured model.
  - Pulls from GPU Ollama server if missing; sets `OLLAMA_HOST=127.0.0.1:11434` and
    restores it in `finally`.
  - Reports failure as Yellow warning; never substitutes a stock model.
  - Does NOT set `CUDA_VISIBLE_DEVICES=-1` (GPU pull must use the GPU).
- Added call `if ($gpuOk) { $null = Ensure-GpuChatModel $StartupGpuModel }` after the
  CPU model ensure block — the launcher is now self-contained for both tiers.

The existing `Start-Server '127.0.0.1:11434'` call already restarts a downed GPU
Ollama server on every launcher re-run. `Ensure-GpuChatModel` adds the model-presence
check on top of that, covering the first-run case where the server starts fresh but the
model has not yet been pulled.

### `router.py`

- Added `routing_reason: d.reason` field to `status()` return dict — exposes the actual
  routing decision reason (why the tier was chosen), separate from `reason` which is the
  `gpu_busy()` signal. Also cached `up()` calls to avoid double-probing both servers.
- Updated `__main__` CLI output to print `routing reason` on its own line.

### `static/index.html`

- Updated the `gpuNote` logic in `refresh()`:
  - **Before**: `!s.gpu_busy ? 'GPU free' : <busy cases>`
  - **After**: adds a middle branch `!s.gpu_server_up ? 'GPU server offline — routing to CPU 8B'`
    so the status pill distinguishes "GPU idle, server up" from "GPU idle but server down".
  - When the GPU server is offline the status dot stays yellow/warn (tier=cpu) and the pill
    text names the actual reason instead of "GPU free" which was misleading.

## Before / after router output

**Before (GPU server down):**
```
GPU busy   : False  — GPU idle (73 MB used, no foreign compute process)
routing to : CPU  huihui_ai/qwen3-abliterated:8b  @ 127.0.0.1:11435
gpu server : down  []
```

**After (GPU server up, 14B available):**
```
GPU busy      : False  — GPU idle (73 MB used, no foreign compute process)
routing to    : GPU  huihui_ai/qwen3-abliterated:14b  @ 127.0.0.1:11434
routing reason: GPU free — GPU idle (73 MB used, no foreign compute process)
gpu server    : up  ['huihui_ai/qwen3-abliterated:14b', ...]
```

## What is unverified

The "after" router output above is the expected state after a launcher restart brings
the GPU Ollama server back up and the 14B is confirmed present. It has not been measured
against a live system in this session. Verify by re-running `python local_agent\router.py`
after the next launcher restart.
