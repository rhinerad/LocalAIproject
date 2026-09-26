# 2026-09-03an — delayed-login reboot proof not obtained (logon ~14s after boot)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: Session-0 / unattended WSL Docker is not proven.** Rhine signed in about 14 seconds after Windows boot, before the BootTrigger PT30S delay. The logon watchdog started WSL first. Farm Redis was not migrated.

## Clock

- Windows `LastBootUpTime`: 2026-09-03T18:32:56.500-04:00
- Winlogon session start (notify event 2): 2026-09-03T18:33:10.7-04:00 (~14s after boot)
- `\local-agent-wsl-docker-logon-watchdog` Last Run: 18:33:11, Status Running, last result 267009 (task still running)
- `\local-agent-wsl-docker-boot` Last Run: 18:33:40 (PT30S after boot), Status Running, last result 267009, Schedule Type At system start up, Run as rhine
- Heartbeat `EVENT=START SOURCE=boot`: 18:33:56 instance `3a1a7506-98ae-47fb-ac4c-9c9e83da3623`
- Heartbeat `EVENT=START SOURCE=watchdog`: 18:35:24 same instance
- Watchdog log for this boot: `18:33:54 RESULT=RESTART reason=dead_or_stale age_sec=219` (stale leftover from previous session `18:30:19 SOURCE=watchdog INSTANCE_ID=3ea5753c-...`), then `WATCHDOG_EXEC_KEEPALIVE`

Pass needed same `INSTANCE_ID` + `SOURCE=boot` heartbeats spanning a ~3 minute lock-screen window, and watchdog `RESULT=ALIVE`. This boot has logon before the boot task, so that bar is not met.

## What this boot still shows

- BootTrigger S4U task `\local-agent-wsl-docker-boot` did fire after this Windows boot (not merely registered).
- After login, WSL instance `3a1a7506-98ae-47fb-ac4c-9c9e83da3623` stayed up with Docker 29.7.2 and probe `wsl-boot-probe` running. Two keep-alive loops (boot + watchdog) wrote the same instance id through 19:11+.
- Pre-reboot leftover: instance `e642f765-...` `SOURCE=boot` until 18:24:42; watchdog rescue at 18:27:18 / 18:29:19 started `3ea5753c-...` (previous session, not this LastBootUpTime).

## Not done

- Delayed-login test still due: reboot, wait ~3 minutes at the lock screen, then sign in. Watchdog must log `RESULT=ALIVE` with a fresh `SOURCE=boot` heartbeat from before logon.
- Do not treat this as Session-0 Redis. Compose / Docker Desktop Redis stay put until that proof exists and Rhine confirms cutover.

Id from `python scripts/next_changelog_id.py` (2026-09-03an). Admin-grant entry remains `2026-09-03y_rhine_added_to_local_administrators.md`.