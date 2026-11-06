# 2026-09-05dr — Farm dashboard default bind is loopback

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dr**. Implements
`2026-09-05dk`. GET-only / no-auth **unchanged**.

## What changed

Default bind is **`127.0.0.1:8765`**, not auto-detected `192.168.50.x`.
LAN candidates are ignored unless `FARM_DASHBOARD_HOST` is set.

Allowed explicit hosts (`FARM_DASHBOARD_HOST` or `--host`):

- `127.0.0.1` (default)
- `10.90.90.1` (WireGuard hub overlay)
- a private home-LAN IPv4 (e.g. `192.168.50.208`)

Still refused: `0.0.0.0`, link-local, other `10.90.90.x` (spoke). Private
LAN firewall rule is created **only** for a LAN opt-in bind.

`Start-FarmDashboard.ps1`, `worker_farm/README.md`,
`docs/FARM_HEALTH_RUNBOOK.md`, `TODO.md` updated.

## Tests

```
python -m unittest local_agent.worker_farm.test_farm_dashboard -v
```

**16/16 OK**, including:

- default is `127.0.0.1` even when `192.168.50.208` is in the candidate list
- `env_host=192.168.50.208` restores LAN opt-in
- `env_host=10.90.90.1` allowed
- a real `ThreadingHTTPServer` on `127.0.0.1:ephemeral` answers loopback
  and **does not** accept a connect on `192.168.50.208` at that port

## Running process

The logon dashboard (pid 28216 on LAN, as of 2026-09-05dh) **still uses
the old bind until restarted.** This PR does not kill it. Restart
`Start-FarmDashboard.ps1` / the logon task to listen on
`http://127.0.0.1:8765/`.

LAN again:

```
$env:FARM_DASHBOARD_HOST = '192.168.50.208'
powershell -File local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
```
