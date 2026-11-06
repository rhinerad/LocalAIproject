# 2026-09-04s — ComfyUI / agent GPU time-sharing via clear_vram (option B)

Date: 2026-09-04. Host: DuranGamingPC. Implementation + unit tests. **Live Rockernow verify is a separate step** (design PR 3).

Design: `docs/COMFYUI_GPU_TIMESHARE_CLEAR_VRAM.md`. Option A (VRAM threshold) remains closed by the 2026-09-04 DynamicVRAM probe (345 MiB through idle/load/loaded-idle; 28.93 s lag after generate start).

## What landed

- `local_agent/mcp_client.py`: `call(..., lock_timeout=, spawn=False)` and `ready()`. Default callers unchanged. `spawn=False` does not handshake. Lock timeout raises `McpError` instead of waiting on an in-flight generate.
- `local_agent/router.py`: `decide()` idle-8188 hook — owners (three PID files, fail-closed unreadable) + MCP `queue`/`list` then urllib `/queue` + already-claimed hop-N or `clear_vram` (`POST /free`) verified at **≤800 MiB**. `gpu_gate.request()` (`timeshare:host-gpu`) **before** `/free`. Farm/Qwythos never `/free`. Kill switch `EQUAL_SHARES_COMFY_TIMESHARE=0`.
- `status()` third state: `8188 up, idle, agent may claim` (read-only, no `/free`).
- `agent.py`: when 8188 is the only busy signal, still read `/api/ps` for hop-N already-loaded. Does not consume the timeshare one-shot grant (that lives in `decide()`).
- Tests: `test_mcp_client.py` (lock/spawn), `test_router_comfy_timeshare.py` (owners, queue, python.exe not foreign, 345 still `/free`, 2459 fail-closed, hop-N, farm skip, PowerInfer occupancy, gpu_gate pending, status third state).

`comfy_listening()`, `gpu_busy()` 8188 short-circuit, `plan_vision_vram`, and `media_*` were not changed.

## Accepted residual (not this change)

TOCTOU between empty-queue check and 14B load; manual Queue Prompt with no OWNER file. See Remaining-unsafe in the design doc.

## Same-session bugs — connection check

1. **Empty content on the CPU tier.** While 8188 listened, `gpu_busy()` forced CPU fallback. This PR would route **idle**-8188 turns onto GPU instead. If empty replies were a CPU-8B/harness-profile failure, timeshare **masks** that path for idle ComfyUI and does not fix a real render’s CPU fallback. Still a separate investigation; do not treat GPU timeshare as the fix.
2. **ComfyUI ignored a detailed prompt + 4 refs and emitted red-mug images.** The 2026-09-04 VRAM probe / live `comfy_generate` used the hardcoded prompt “a small red ceramic mug…”. That is `comfy_generate` / MCP `generate_image` payload handling, not `gpu_busy()`/`decide()` CPU fallback. Unrelated to this hook unless a later check shows the MCP client reused the probe prompt.
