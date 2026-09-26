# 2026-09-04ac â€” farm dashboard logon task `\local-agent-farm-dashboard` (03am-style verify)

Date: 2026-09-04. Host: DuranGamingPC. All times America/New_York (UTC-4). No `schtasks /Run`, no `Start-ScheduledTask` on the dashboard task during the sign-out/in cycle.

Id from `python scripts/next_changelog_id.py --date 2026-09-04` immediately before write: **2026-09-04ac**.

**Result: FAIL.** dashboard did not self-start on logon

Mirrors `\local-agent-farm-status-daemon`: Interactive LogonTrigger, InteractiveToken, RunAs rhine, Limited, Hidden, RestartCount 999 / PT1M, ExecutionTimeLimit PT0S, StopOnIdleEnd false, MultipleInstances IgnoreNew, StartWhenAvailable. Action launches `dashboard\Start-FarmDashboard.ps1` via `dashboard\run_farm_dashboard_task.cmd`.

Same bar as `2026-09-03am` (relay): real Type-2 cycle; leftovers from the prior manual start gone; Last Run aligned with new explorer, not a `/Run` leftover; task owns the live listener.

## Clock

- Evidence at: 2026-09-06 11:25:23.738
- explorer: pid 11812 start=2026-09-06 11:22:47
- Type-2 4624 after baseline: (none)
- `\local-agent-farm-dashboard` Last Run: 2026-09-06 11:22:47, State Running, last result 267009, Interactive / rhine / MSFT_TaskLogonTrigger
- `\local-agent-farm-status-daemon` Last Run: 2026-09-06 11:22:47 State Running result 267009
- `\local-agent-tunnel-relay` Last Run: 2026-09-06 11:22:47 State Running result 267009
- Leftover manual dashboard pids (must be gone): 22300, 27032, 29096, 30108 gone=True
- Last Run aligned with explorer (delta<=15s): True

## Listen / API

- :8765: 
- GET /api/dashboard: (no api)

## Task action

- Execute: C:\Windows\System32\cmd.exe
- Arguments: /c "A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\local_agent\worker_farm\dashboard\run_farm_dashboard_task.cmd"
- `farm_dashboard_task_run.log`:

```
START Sun 09/06/2026 11:22:57.32 session= 
durangamingpc\rhine
cd_before=A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09 
cd_after=A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09 
SCRIPT_OK
launching

```

## Accepted limitation

Same as farm-status and tunnel-relay: no pre-login / S4U / At-startup. Dashboard starts at interactive logon for rhine, not before the desktop session exists.

## Files

- Windows Task Scheduler: `\local-agent-farm-dashboard` (host, not in git)
- `local_agent/worker_farm/dashboard/run_farm_dashboard_task.cmd`
- `local_agent/worker_farm/dashboard/Start-FarmDashboard.ps1` (unchanged)
