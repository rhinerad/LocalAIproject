# 2026-09-03f — persist farm_status_daemon as a per-user Windows Scheduled Task

Date: 2026-09-03. Host configuration only; no Python source changed. Not a Windows Service. `tunnel_relay` was not installed or changed.

## What changed

Registered Task Scheduler task `local-agent-farm-status-daemon` in the task-library root (`\`), not under `\Microsoft\Windows\...`.

- User: `DURANGAMINGPC\rhine`. LogonType Interactive (InteractiveToken). RunLevel Limited. Not SYSTEM. Not Highest privileges. Not "run whether user is logged on or not".
- Trigger: At log on of `DURANGAMINGPC\rhine` only.
- Hidden: yes.
- Restart on failure: every 1 minute, RestartCount 999.
- StartWhenAvailable: yes (run as soon as possible after a missed start).
- ExecutionTimeLimit: `PT0S` (disabled). The default 72h limit would have killed the forever-loop daemon.
- MultipleInstances: IgnoreNew.
- Working directory: repository root (required for `-m local_agent.worker_farm.farm_status_daemon`).

Action (cmd wrapper because Scheduled Task actions do not redirect well by themselves):

- Execute: `C:\Windows\System32\cmd.exe`
- Arguments: `/c set PYTHONUNBUFFERED=1&& "<repo>\local_agent\worker_farm\.venv\Scripts\python.exe" -u -m local_agent.worker_farm.farm_status_daemon >> "<repo>\local_agent\worker_farm\runtime\farm_status_daemon.log" 2>&1`
- Start in: repository root

`local_agent/worker_farm/runtime/` is already gitignored in `local_agent/worker_farm/.gitignore` (`runtime/`). The directory already existed; log file is `local_agent/worker_farm/runtime/farm_status_daemon.log`.

No `--once`. Interval and fail-alert-after left at daemon defaults.

## Why

The daemon is a forever loop that writes `local_agent/worker_farm/farm_status.json`. It was not persisted as a per-user logon task, so it would not start after logon and was not running tonight.

## Evidence

`Register-ScheduledTask` (ScheduledTasks cmdlets, not bare `schtasks /create`). `Export-ScheduledTask` XML after register:

- `<URI>\local-agent-farm-status-daemon</URI>`
- Principal `LogonType` InteractiveToken; Get-ScheduledTask RunLevel Limited; UserId is this machine's `rhine` SID
- `<Hidden>true</Hidden>`
- `<RestartOnFailure><Count>999</Count><Interval>PT1M</Interval></RestartOnFailure>`
- `<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>`
- `<StartWhenAvailable>true</StartWhenAvailable>`
- `<MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>`
- `<LogonTrigger><UserId>DURANGAMINGPC\rhine</UserId></LogonTrigger>`
- Exec `C:\Windows\System32\cmd.exe` with WorkingDirectory = repository root

RestartCount 999 stuck on Register (no XML patch needed).

## Verified after

1. `Start-ScheduledTask -TaskName local-agent-farm-status-daemon` succeeded. State `Running`. LastRunTime 2026-09-03 3:11:54 AM ET. LastTaskResult 267009 (still running).
2. Process: `cmd.exe` wrapping venv `python.exe -u -m local_agent.worker_farm.farm_status_daemon` (python PID 22564; child interpreter PID 37500).
3. First log lines (no crash, no secrets):

```
broker reachable: yes  workers responding: no  latency_ms: 1318.7  error: broker reachable, no worker answered ping  checked_at: 2026-09-03T07:11:56.928795+00:00
broker reachable: yes  workers responding: no  latency_ms: 1202.0  error: broker reachable, no worker answered ping  checked_at: 2026-09-03T07:12:28.454420+00:00
```

The daemon is looping on the default ~30s interval. `workers responding: no` is farm worker state, not a daemon crash.

## Still unverified

- Real logoff/logon start (this session used `Start-ScheduledTask` while already logged on).
- Windows default IdleSettings remain (StopOnIdleEnd true, idle Duration PT10M). Not requested in the task spec; not changed.

## Files

- `CHANGELOG/2026-09-03f_windows_farm_status_daemon_task.md` (this entry)
- Windows Task Scheduler: `\local-agent-farm-status-daemon` (host, not in git)
- `local_agent/worker_farm/runtime/farm_status_daemon.log` (gitignored)