# 2026-09-04q — ComfyUI / agent GPU timeshare via `clear_vram` (mocked)

Date: 2026-09-04. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py`: **2026-09-04q**.
Design: `docs/COMFYUI_GPU_TIMESHARE_CLEAR_VRAM.md`.

**Live Rockernow verify was not run this pass.** No live ComfyUI, nvidia-smi,
or MCP child in the new tests.

## What changed

- `local_agent/mcp_client.py`: instance and module `call(..., lock_timeout=, spawn=)`.
  `spawn=False` fails closed without `_ensure_started` / 120 s handshake.
  `lock_timeout` bounds `Lock.acquire` and raises `McpError` on failure.
  Existing `comfy_*` tools omit the kwargs (unchanged spawn-on-first-use).
- `local_agent/router.py`: numbered `decide()` order — `gpu_busy()`, classify
  once, farm-skip the hook, else timeshare, then `skip_gpu_inventory` from
  post-hook `busy`. Helpers `_owners_idle_for_timeshare`, `_comfy_queue_idle`,
  `_clear_vram_for_timeshare`, `try_idle_comfy_timeshare`.
- Occupancy before `/free`: nvidia-smi `None` fail-closed; unexplained VRAM
  (not ≤800, not 2000–3200, not already-claimed Ollama/PI) fail-closed;
  ComfyUI python paths waived; `Python312\python.exe` foreign; bare
  `python.exe` + 8188 is not foreign by name (band still applies).
- Successful claim logs WARNING on `local_agent.router.timeshare` that the
  sidebar `gpu_gate` card did not fire (interim bypass). `agent.py` is
  unchanged.
- Kill switch `EQUAL_SHARES_COMFY_TIMESHARE` default-on; `=0` disables.

## Why

`gpu_busy()` treats listening 8188 as busy, so idle ComfyUI parks every
GPU-routed turn on CPU. Option A (VRAM threshold) is closed: used stays
345 MiB through the claim window. Option B tests owner + queue, then
`POST /free`, then loads.

## Tests

Mocked only (`local_agent/test_router_comfy_timeshare.py`). Existing
`test_mcp_client.py` covers `lock_timeout` / `spawn=False`.

## Follow-ups (TODO.md)

- `agent.py` `gpu_gate` when 8188-only busy and timeshare would claim.
- `status()` third badge state from owner+queue, no `/free`.
