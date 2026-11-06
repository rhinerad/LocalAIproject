# 2026-09-03n — farm status dashboard (LAN :8765)

Stdlib-only local farm monitoring dashboard on DuranGamingPC.

## What

- `local_agent/worker_farm/dashboard/` — `server.py` (system Python + `ThreadingHTTPServer`), `collect.py` (poll helpers), `index.html` (dark ops UI), `Start-FarmDashboard.ps1`.
- Binds **private LAN IPv4 only** (detect via `Get-NetIPAddress`; never `0.0.0.0`, loopback, `10.90.90.x`, or APIPA). Port **8765**. Env: `FARM_DASHBOARD_HOST`, `FARM_DASHBOARD_PORT`. Prints `http://<lan-ip>:8765/` on startup.
- Data sources (no reimplemented Celery/Redis probes):
  - `farm_status.json` (always re-read; stale if missing or `checked_at` age > 90s → daemon-down)
  - last 20 `FARM_STATUS_OUTAGE` / `FARM_STATUS_RECOVERED` lines from `farm_status_daemon.log`
  - `farm_health --json` via farm venv subprocess (30s cache, ~8s timeout) for registered tasks
  - WireGuard hub via `Get-Service WireGuardTunnel$hub`; spoke inferred from workers / recent relay peer `10.90.90.2`; tunnel_relay via process cmdline + listen on `10.90.90.1:6379`; Redis from snapshot `broker_reachable` (+ optional docker ps secondary)
- API: `GET /api/dashboard` combined JSON; `GET /` HTML. Per-section errors so one failure never blanks the page.
- Private-profile Windows Firewall rule for TCP 8765 attempted at start (Access Denied reported, server still starts).
- Tests: `local_agent/worker_farm/test_farm_dashboard.py` (outage parse, stale >90s, bind rejection, event cap 20).

## How to start

```
powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
```

Or system Python:

```
A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe local_agent\worker_farm\dashboard\server.py
```

Do not run the dashboard from the farm venv. Do not attach to :8760.

## Why

Phone/other home-network devices need a live view of hub / spoke / relay / Redis / workers / registered tasks without SSHing or reading logs by hand. Separate cards make "Redis up, Mac/relay dead" obvious.