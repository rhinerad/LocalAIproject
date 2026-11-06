# 2026-09-03au - WSL Docker-at-boot delayed-login proof PASS (watchdog ALIVE)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: PASS.** `\local-agent-wsl-docker-boot` fired at boot, kept WSL Docker alive through a ~6 minute lock-screen window, and the logon watchdog logged `RESULT=ALIVE` (not `RESTART`) after delayed sign-in.

This finishes what the mid-stream reboot left open. `2026-09-03at` recorded the unattended keep-alive at T+274s, before interactive logon, so watchdog `ALIVE` was still empty. After sign-in, that last bar is met. Prior not-proven boots: `2026-09-03an` (logon +14s), `2026-09-03ao` (logon +11s).

This session did **not** issue a second restart. Bot 10 already initiated a real reboot (`shutdown /r`) at 20:57:54; this entry is the post-sign-in verification of that boot.

## Clock

- Windows `LastBootUpTime`: 2026-09-03 20:59:02.500
- Event 1074: 20:57:54 `C:\WINDOWS\system32\shutdown.exe` restart on behalf of `DuranGamingPC\rhine` (comment: wait 3 minutes at lock screen). Kernel-General 12 OS start: 20:59:03. `HiberbootEnabled=0` (not Fast Startup / hybrid).
- Pre-reboot mark in `heartbeat.log` / `start.log` / `watchdog.log`: `=== PRE-REBOOT MARK 2026-09-03T20:57:54-04:00 retry4-enforce-180s-lockscreen-wait ===`
- `\local-agent-wsl-docker-boot` still registered and Enabled. `schtasks /query /tn "\local-agent-wsl-docker-boot" /v /fo LIST`: Status Running, Last Run Time 9/3/2026 8:59:44 PM, Last Result 267009 (`SCHED_S_TASK_RUNNING` / 0x41301 — keep-alive still running, not a failed exit), Run As User `rhine`, Schedule Type At system start up. `Get-ScheduledTask`: LogonType **S4U**, UserId `rhine`, Trigger `MSFT_TaskBootTrigger` delay `PT30S`, action `C:\Program Files\WSL\wsl.exe -d Ubuntu-24.04 --exec /bin/bash .../keep-alive.sh boot`. Rhine is in local Administrators (`2026-09-03y`).
- Last Run 20:59:44 is 42s after `LastBootUpTime` (PT30S plus WSL start). User Profile Service loaded `ntuser.dat` at 20:59:44 — that is the S4U task profile, **not** interactive session 1.
- Heartbeat `EVENT=START SOURCE=boot`: 21:00:02 instance `d168e3cc-a6e8-402a-bfc1-28295d81c09e`
- First `SOURCE=boot` heartbeat with Docker: 21:00:11 `DOCKER=29.7.2 PROBE=true`
- `2026-09-03at` snapshot at 21:03:36: explorer not running; `SOURCE=boot` span 199s; watchdog ALIVE empty
- Interactive logon (Winlogon notify event 2, User Profile Service session 1, explorer start): **21:05:16** (+374s after boot). 180s lock-screen bounce ended 21:02:02.
- `\local-agent-wsl-docker-logon-watchdog` Last Run: 21:05:17, Result 0, State Ready, LogonType Interactive, trigger `MSFT_TaskLogonTrigger`
- Watchdog `RESULT=ALIVE` 21:05:18 `reason=heartbeat_fresh_docker_up_probe_running age_sec=6 docker=29.7.2 probe=true instance_now=d168e3cc-a6e8-402a-bfc1-28295d81c09e last=2026-09-03T21:05:13-04:00 SOURCE=boot`. No `RESULT=RESTART` and no `EVENT=START SOURCE=watchdog` after this boot.
- Post-sign-in verification 21:21:22: same boot task still Running / Last Run 20:59:44 / Last Result 267009. `SOURCE=boot` heartbeats for `d168e3cc-...` count=121, last=21:21:13 (span from 21:00:11 ≈ 1262s). `docker info`: ServerVersion=29.7.2, ContainersRunning=1, Driver=overlayfs. `docker ps`: `wsl-boot-probe Up 19 minutes alpine:3.21`. `status.json` source=boot, same instance.

## Pass bar (from an/ao)

Same `INSTANCE_ID` + `SOURCE=boot` heartbeats spanning a ~3 minute lock-screen window, **and** watchdog `RESULT=ALIVE` after delayed sign-in. Login-rescue is excluded: interactive session 1 landed at +374s, after BootTrigger had already been writing `SOURCE=boot` heartbeats from 21:00:11.

| Check | an / ao | this boot |
| --- | --- | --- |
| Real restart (1074 + Kernel-General 12) | yes | yes (20:57:54 / 20:59:03) |
| BootTrigger Last Run after LastBootUpTime | yes | 20:59:44 (+42s) |
| Interactive logon vs PT30S | +14s / +11s (watchdog first) | +374s (boot task first) |
| `SOURCE=boot` unattended span | raced | 21:00:11 → 21:05:16+ (and still running) |
| Watchdog after sign-in | `RESULT=RESTART` then own keep-alive | `RESULT=ALIVE` same instance |

## Notes

- Fast Startup is disabled (`HiberbootEnabled=0`). A: is a fixed NTFS volume (profile `A:\Users\rhine`), so the probe dir is reachable without a mapped-drive logon.
- The one-shot flag `enforce-lockscreen-wait.flag` was deleted after the 180s window. Later boots are not bounced.
- `schtasks` prints Logon Mode `Interactive/Background` for this task; that is the S4U display. `Get-ScheduledTask` Principal.LogonType is `S4U`.
- Farm Redis / Docker Desktop compose was **not** migrated in this step. This proof is WSL Docker CE on Ubuntu-24.04 via `\local-agent-wsl-docker-boot`, not Session-0 farm Redis.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03au** (claimed 21:18:39; file written after delayed-logon evidence). Early auto-PASS: `2026-09-03at`. Prior not-proven: `2026-09-03an`, `2026-09-03ao`. Admin grant: `2026-09-03y`.
