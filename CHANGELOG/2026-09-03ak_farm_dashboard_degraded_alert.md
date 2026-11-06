# 2026-09-03ak — farm dashboard degraded-health alert

Follow-up to `2026-09-03n` (dashboard) and `2026-09-03v` (phone reached).
Letter reconfirmed with `python scripts/next_changelog_id.py` immediately
before this file (`aj` already taken by three parallel entries).

## What

Lightweight alert when the LAN dashboard sees the farm as not healthy.
Stdlib only. No new dependencies. No second health definition.

Degraded = the existing `/api/dashboard` overall block is not `ok`:
`overall.status != "ok"` or `overall.stale` (daemon-down / missing snapshot).
No extra latency cutoff and no missing-task alert.

Edge-triggered:

```
FARM_DASHBOARD_DEGRADED status=no_workers stale=false latency_ms=1400 error=quiet
FARM_DASHBOARD_RECOVERED status=ok
```

Stay-degraded polls are silent. First observation after start fires if the
farm is already down. Best-effort Windows balloon via built-in WinForms
(`System.Windows.Forms.NotifyIcon`); failure never breaks the HTTP handler.
A 30s watch thread reads `farm_status.json` so this works without a browser
open. HTTP `/api/dashboard` uses the same alerter (no double-fire).

Restart the dashboard process to pick this up:

```
powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
```

## Tests

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_dashboard -v
```

13 tests, OK (0.000s). New cases: ok vs stale/non-ok, daemon-down from a
stale snapshot, edge-triggered degraded/recovered, no recovered on a healthy
start, redis-password redaction on the greppable line.

## Files

- `local_agent/worker_farm/dashboard/collect.py`
- `local_agent/worker_farm/dashboard/server.py`
- `local_agent/worker_farm/test_farm_dashboard.py`
- `local_agent/worker_farm/README.md`
