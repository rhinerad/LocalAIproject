# 2026-09-03h — farm-status idle-stop off; leftover tunnel_relay stopped; S4U startup task blocked

Date: 2026-09-03. Host Task Scheduler / process control only; no Python source changed. No reboot.

## What changed

1. Task `\local-agent-farm-status-daemon`: `IdleSettings.StopOnIdleEnd` set to `false` (idle Duration no longer stops the task). Everything else kept: logon trigger for `DURANGAMINGPC\rhine`, InteractiveToken, Hidden, RestartCount 999 / PT1M, ExecutionTimeLimit PT0S, MultipleInstances IgnoreNew.

2. Stopped leftover `python.exe` PID **37480** running `local_agent/worker_farm/relay/tunnel_relay.py --bind-ip 10.90.90.1` (system Python312, parent Git Bash 37072). After stop, Win32_Process had no other `tunnel_relay.py` command lines. Unrelated python (farm_status_daemon, server.py, media_watcher) was not killed.

3. Approved task `\local-agent-tunnel-relay` (At startup / LogonType S4U / RunLevel Limited / not Interactive / not SYSTEM) was **not** registered. S4U `Register-ScheduledTask` failed with Access is denied. Retry `-Xml -Force` failed the same (CimException PermissionDenied). COM `RegisterTaskDefinition` with TASK_LOGON_S4U also Access is denied (HRESULT 0x80070005). Did not fall back to Interactive/logon or SYSTEM. Task remains missing. Bind left free; no new listener started.

## Why

The farm-status task still had default idle-stop (`StopOnIdleEnd` true), so an idle timeout could kill the forever-loop daemon. The leftover relay was a Git-Bash python, not a Scheduled Task. Persistence was supposed to be an S4U startup task so it runs whether or not an interactive session is present; this non-elevated session cannot create that principal.

## Evidence

`Set-ScheduledTask` on the existing farm-status definition (process left running). `Export-ScheduledTask` IdleSettings after the change:

```
<IdleSettings>
  <Duration>PT10M</Duration>
  <WaitTimeout>PT1H</WaitTimeout>
  <StopOnIdleEnd>false</StopOnIdleEnd>
  <RestartOnIdle>false</RestartOnIdle>
</IdleSettings>
```

Also still present on that task: InteractiveToken, Hidden true, RestartCount 999 / PT1M, ExecutionTimeLimit PT0S, IgnoreNew, LogonTrigger `DURANGAMINGPC\rhine`.

Bind 10.90.90.1:6379:

- Before stop: Listen + many Established, OwningProcess 37480 (`python.exe` `tunnel_relay.py --bind-ip 10.90.90.1`).
- After stop: `Get-NetTCPConnection -LocalAddress 10.90.90.1 -LocalPort 6379` empty. PID 37480 gone.
- Adapter `hub` Status Up; `10.90.90.1/28` still assigned. Task start was skipped because registration failed (hub was not down).

S4U errors (verbatim):

- `Register-ScheduledTask` principal S4U: `Access is denied.`
- `Register-ScheduledTask -Xml -Force`: `Access is denied.` / `PermissionDenied: (PS_ScheduledTask:Root/Microsoft/...S_ScheduledTask) [Register-ScheduledTask], CimException`
- COM: `Access is denied. (Exception from HRESULT: 0x80070005 (E_ACCESSDENIED))`

## Verified after

1. `\local-agent-farm-status-daemon` State `Running`. Daemon process still up: cmd PID 15684 wrapping venv python PID **22564** (`-m local_agent.worker_farm.farm_status_daemon`); child interpreter PID 37500. Not killed.
2. No `\local-agent-tunnel-relay` task. No `tunnel_relay.py` process. 10.90.90.1:6379 has no Listen/Established.
3. venv `local_agent/worker_farm/.venv/Scripts/python.exe` and `local_agent/worker_farm/relay/tunnel_relay.py` exist; runtime dir exists. Not used because the task did not register.

Does not claim Docker/Redis/Mac-worker persistence. Mac reconnect to 10.90.90.1:6379 was not re-established after the leftover stop (no listener).

## Still unverified

- Creating `\local-agent-tunnel-relay` from an elevated session, or after "Log on as a batch job" is granted for `DURANGAMINGPC\rhine`.
- Task start, new PID, Listen on 10.90.90.1:6379 owned by that PID, and `local_agent/worker_farm/runtime/tunnel_relay.log` bind line.
- Real reboot/startup trigger (not attempted; no reboot).

## Files

- `CHANGELOG/2026-09-03h_farm_status_idle_stop_and_tunnel_relay_task.md` (this entry)
- Windows Task Scheduler: `\local-agent-farm-status-daemon` (host, StopOnIdleEnd patched; not in git)
- Windows Task Scheduler: `\local-agent-tunnel-relay` **not created**