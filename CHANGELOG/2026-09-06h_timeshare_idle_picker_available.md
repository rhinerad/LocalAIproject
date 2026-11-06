# 2026-09-06h — Timeshare-idle status keeps GPU picker selectable

Date: 2026-09-06. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06h**.

## Symptom

With Rockernow ComfyUI merely listening on `:8188` (empty queue, no live
owner, `timeshare_idle: true`), `/api/status` still set
`include_gpu = not gpu_busy`. `gpu_busy()` short-circuits True on the TCP
listener before timeshare. After a restart (empty
`_LAST_VERIFIED_GPU_MODELS`), `chat_models()` labeled
`huihui_ai/qwen3-abliterated:14b` as **GPU currently unavailable** /
`available: false`, so the operator could not select GPU chat models even
though Option B allows a granted turn to claim.

## Root cause (verified)

`router.status()` used `include_gpu = not busy` only. The third-state badge
(`timeshare_idle`) did not reopen the GPU catalogue. Empty display cache +
busy-8188 ⇒ primary 14B forced into the disabled picker branch around
`router.py` chat_models listing.

Confirmed offline: empty cache + live idle 8188 ⇒ `available: false` with
label "GPU currently unavailable"; same probe with `include_gpu=True` ⇒
`available: true` and real GPU tags.

## Fix

Smallest change in `router.status()`:

- Compute `timeshare_idle` first.
- `include_gpu = (not busy) or timeshare_idle`.

Active render busy (no timeshare third state) still skips the GPU catalogue.
`gpu_busy()` / `render_story_image` foreign-8188 preflight unchanged.
Routing still uses `decide(ensure_gpu_evicted=False)` on status (no `/free`);
a real chat turn still claims via timeshare + sidebar `gpu_gate`.

## Files

- `local_agent/router.py` — status include_gpu for timeshare_idle
- `local_agent/test_router_status_busy.py` — idle picker available; active
  render still skips catalogue
- `local_agent/server.py` — `APP_REVISION=2026-09-06-timeshare-idle-picker-r88`
- `local_agent/START_LOCAL_AGENT_GUI.ps1` — matching ExpectedAgentRevision

## Tests

`python -m unittest test_router_status_busy test_router_switching
test_router_comfy_timeshare test_agent_timeshare_gpu_gate
test_launcher_revision`: **116/117** pass. Failure is pre-existing
`test_coding_mode_selects_coding_model_when_gpu_idle` (decide/coding path;
unchanged by this patch). New tests:
`test_timeshare_idle_status_keeps_gpu_picker_available_without_cache`,
`test_active_render_busy_still_skips_gpu_catalogue` — both ok.

## Live verify

After `START_LOCAL_AGENT_GUI.ps1` restart to r88: with idle 8188,
`timeshare_idle: true`, 14B `available: true` without
`unavailable_reason` / "GPU currently unavailable". Documented in
GROK_STATUS.md.

## Live verify (2026-09-06 ~6:15 PM ET)

Restart via `local_agent/START_LOCAL_AGENT_GUI.ps1` → PID 36092 on :8760,
`APP_REVISION=2026-09-06-timeshare-idle-picker-r88`. Rockernow :8188 left up
with empty queue; nvidia-smi util 0%.

`/api/status` snippets:

```json
{
  "gpu_busy": true,
  "timeshare_idle": true,
  "reason": "8188 up, idle, agent may claim",
  "app_revision": "2026-09-06-timeshare-idle-picker-r88",
  "chat_models": [
    {"name": "huihui_ai/qwen3-abliterated:14b", "available": true, "gpu": true, "gpu_only": true},
    {"name": "gpt-oss-20b-heretic:latest", "available": true, "gpu": true, "gpu_only": true}
  ]
}
```

14B has no `unavailable_reason` and no "GPU currently unavailable" label.
Observational `tier` remains `cpu` / 8B until a granted chat turn claims
(unchanged Option B status contract).
