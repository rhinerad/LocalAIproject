# 2026-09-03s — tunnel-relay registered as logon/Interactive under rhine

All times America/New_York (UTC-4). No reboot. No logoff. Did not change `\local-agent-farm-status-daemon`.

Id from `python scripts/next_changelog_id.py` → `2026-09-03s` (letter `r` already taken by a parallel entry).

## Intent

Prior plan was S4U At-startup for `\local-agent-tunnel-relay`; that path stayed blocked (`Access is denied` / `0x80070005` for rhine S4U — see `2026-09-03p`). Rhine approved the fallback: **LogonTrigger + InteractiveToken** under `DURANGAMINGPC\rhine`, mirroring `\local-agent-farm-status-daemon`.

## Registration

Registered as rhine (no UAC / no tiffa). Task did not previously exist.

| Field | Value |
| --- | --- |
| Name | `\local-agent-tunnel-relay` |
| UserId | `rhine` (SID matches farm-status) |
| LogonType | Interactive / InteractiveToken |
| RunLevel | Limited |
| Trigger | MSFT_TaskLogonTrigger for `DURANGAMINGPC\rhine` (not BootTrigger) |
| Hidden | true |
| RestartOnFailure | Count 999 / Interval PT1M |
| ExecutionTimeLimit | PT0S |
| StopOnIdleEnd | false |
| MultipleInstances | IgnoreNew |
| StartWhenAvailable | true |
| AllowStartIfOnBatteries / DontStopIfGoingOnBatteries | true |
| Execute | `C:\Windows\System32\cmd.exe` |
| Arguments | `/c set PYTHONUNBUFFERED=1&& "<venv python>" -u "<relay script>" --bind-ip 10.90.90.1 >> "<log>" 2>&1` |
| WorkingDirectory | repo root |
| Python | `local_agent/worker_farm/.venv/Scripts/python.exe` (confirmed present; not system Python312 as the task Execute) |
| Script | `local_agent/worker_farm/relay/tunnel_relay.py` |
| Log | `local_agent/worker_farm/runtime/tunnel_relay.log` |

XML export matches farm-status principal/trigger/settings shape; action paths are relay-specific.

## Start verification

Baseline before work: hub `10.90.90.1` Preferred; Listen `10.90.90.1:6379` owned by python **36984** (manual tree `43704→32408→36984`); Established ~35; farm-status task Running.

1. `schtasks /Run` with manual still holding bind: launch SUCCESS; LastTaskResult **1**; Listen stayed 36984 (expected bind conflict).
2. Stopped **only** processes whose CommandLine contains `tunnel_relay.py` (not farm_status). Bind freed.
3. `schtasks /Run` with bind free (multiple attempts): task State **Running**, process tree appeared (`cmd` → venv `python.exe` → system Python312 child, same pattern as manual), but **no Listen** on `10.90.90.1:6379` within 20+ seconds; CPU near idle; log did not gain a new `relaying` line while those task instances were alive. LastTaskResult after forced stop: **4294967295** (-1).
4. Per fallback rule: stopped hung task instances (`Stop-ScheduledTask` + process kill) and **restored manual** listener via the same cmd/venv/`--bind-ip 10.90.90.1` command line in background.

## Live path after this change

- Task **registered** and Ready (will also fire at next interactive logon for rhine).
- Live Listen owner: python **41248** (manual restore tree `36712 cmd → 37072 venv python → 41248`).
- Log: `relay relaying 10.90.90.1:6379 -> 127.0.0.1:6379`; Mac connections from `10.90.90.2` resumed.
- Established on hub after restore: 9 (recovering from the free-bind cut).
- `farm_status_daemon` remained up throughout; farm-status task still Running.

## Verdict

**PARTIAL.** Registration and settings verification succeeded (logon/Interactive under rhine). Functional Listen from a task `/Run` did **not** succeed in-session; manual listener is the live path again. Does not claim pre-login relay, Docker/Redis changes, or Mac persistence.

