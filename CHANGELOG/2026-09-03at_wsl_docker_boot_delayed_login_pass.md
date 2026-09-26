# 2026-09-03at - WSL Docker-at-boot delayed-login proof PASS

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: PASS.** BootTrigger keep-alive spanned ~3 min unattended; watchdog ALIVE not yet observed

This finishes the reboot proof left mid-stream after `2026-09-03an` / `2026-09-03ao` (logon at +14s / +11s, before BootTrigger PT30S). A one-shot flag bounced interactive logon until 180s after `LastBootUpTime` so BootTrigger S4U could be distinguished from the logon watchdog.

## Clock

- Windows `LastBootUpTime`: 2026-09-03 20:59:02.500
- Evidence collected at: 2026-09-03 21:03:36.050 (elapsed 274s)
- `\local-agent-wsl-docker-boot` Last Run: 2026-09-03 20:59:44, Status Running, last result 267009, S4U / rhine / MSFT_TaskBootTrigger delay=PT30S
- `\local-agent-wsl-docker-logon-watchdog` Last Run: 2026-09-03 20:25:24, Status Ready, last result 1073807364
- Heartbeat `EVENT=START SOURCE=boot`: 2026-09-03 21:00:02 instance `d168e3cc-a6e8-402a-bfc1-28295d81c09e`
- First `SOURCE=boot` heartbeat: 2026-09-03 21:00:11
- Last `SOURCE=boot` heartbeat: 2026-09-03 21:03:30 (count=20, span=199s, dockerOk=True)
- Watchdog keep-alive START: 
- Watchdog `RESULT=ALIVE`: 
- Watchdog `RESULT=RESTART`: 
- explorer running at collection: False start=

## Pass bar (from an/ao)

Same `INSTANCE_ID` + `SOURCE=boot` heartbeats spanning a ~3 minute lock-screen window, and watchdog `RESULT=ALIVE` after delayed sign-in. Login-rescue is excluded only if interactive auth does not land before BootTrigger has been alive unattended.

## Notes

- Fast Startup is disabled (`HiberbootEnabled=0`). A: is a fixed NTFS volume (profile `A:\Users\rhine`), so the probe dir is reachable without a mapped-drive logon.
- The one-shot flag `enforce-lockscreen-wait.flag` is deleted after the window. Later boots are not bounced.
- Farm Redis was not migrated in this step.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03at**. Prior not-proven: `2026-09-03an`, `2026-09-03ao`. Admin grant: `2026-09-03y`.
