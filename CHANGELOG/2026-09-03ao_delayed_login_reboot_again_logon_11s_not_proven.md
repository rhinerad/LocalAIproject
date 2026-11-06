# 2026-09-03ao — delayed-login reboot still not proven (auth ~11s after boot)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: Session-0 / unattended WSL Docker is still not proven.** Same failure mode as `2026-09-03an`: interactive sign-in happened about 11 seconds after Windows boot, before the BootTrigger PT30S delay finished, so the logon watchdog ran first. Farm Redis was not migrated.

## Clock

- Windows `LastBootUpTime`: 2026-09-03T19:50:20.500-04:00
- Winlogon Authentication started / stopped Result 0: 19:50:31
- Winlogon session start (notify event 2): 19:50:32.35
- `\local-agent-wsl-docker-logon-watchdog` Last Run: 19:50:32, Status Running, last result 267009
- `\local-agent-wsl-docker-boot` Last Run: 19:51:02 (PT30S), Status Running, last result 267009, At system start up, Run as rhine
- Heartbeat `EVENT=START SOURCE=boot`: 19:51:12 instance `c536f1c3-d8ce-4331-bf5d-66d1df3e64b1`
- Heartbeat `EVENT=START SOURCE=watchdog`: 19:53:32 same instance
- Watchdog log: `19:51:12 RESULT=RESTART reason=dead_or_stale age_sec=82` (last pre-boot leftover `19:49:52 SOURCE=boot INSTANCE_ID=3a1a7506-...`), then `WATCHDOG_EXEC_KEEPALIVE`
- Prior mark: `PRE-REBOOT MARK 2026-09-03T19:12:06-04:00 retry-delayed-login`

Pass needed ~3 minutes at the lock screen with no interactive auth, `SOURCE=boot` heartbeats spanning that window, and watchdog `RESULT=ALIVE`. Auth at +11s fails that bar.

## What this boot still shows

- BootTrigger S4U task fired again after reboot (Last Run 19:51:02).
- After the race, instance `c536f1c3-...` stayed up with Docker 29.7.2 and probe running (status.json `source=boot` through 20:04+).
- That is not unattended proof while logon precedes the boot task.

## Not done

- Redo: reboot, **do not authenticate for ~3 minutes** after the lock screen appears, then sign in and re-check.
- Compose / Docker Desktop Redis stay put until that proof exists and Rhine confirms cutover.

Id from `python scripts/next_changelog_id.py` (2026-09-03ao). Prior not-proven: `2026-09-03an`. Admin grant: `2026-09-03y`.