# 2026-09-03z - Mac headless LaunchDaemons (ollama + celery survive GUI login)

Date: 2026-09-03. Host: Louises-MBP. All times America/New_York (UTC-4).

Converted `com.local-agent.celery-worker` and `com.local-agent.ollama` (live label; not `ollama-serve`) from user LaunchAgents to `/Library/LaunchDaemons` with `UserName=rhineduran` `GroupName=staff` (uid 503).

Disk letters already present today: a-y (incl. duplicate `h` titles; earlier same-day `r` collision risk noted). `scripts/next_changelog_id.py` was slow/hung on this write; first free letter on disk is **z**. Filename: `CHANGELOG/2026-09-03z_mac_headless_launchdaemons.md`.

Did **not** open Ollama.app. Did **not** start gui LaunchAgents. Did **not** reboot for this check. Did **not** `sudo rm /etc/kcpassword` (Rhine lacks passwordless sudo; cleanup deferred).

## Cold boot (nobody at GUI)

- `kern.boottime` = **Thu Sep 3 15:53:17 2026**. `autoLoginUser` gone (defaults key does not exist).
- Both system LaunchDaemons started **15:53:49** (~32s after boot), uid 503, `runs=1`, state running, last exit never.
  - ollama pid **336** -> `127.0.0.1:11434` HTTP **200**
  - celery wrapper/python pid **339**; children 582/585 ~15:54:07-09
  - celery ready line: `[2026-09-03 15:54:18,506: INFO/MainProcess] celery@Louises-MBP ready.` (Redis connected)
- Pre-login snapshot at login window matched these pids/starts.

## Post GUI login (PASS - pids held)

Rhine GUI-logged in ~**15:58** (`stat -f %Su /dev/console` -> `rhineduran`; `who` console/ttys from Sep 3 15:58). Check at **16:00:16 ET** (`uptime` ~7 min):

| Job | pid | uid | lstart | runs | vs boot 15:53:17 | vs login ~15:58 |
| --- | --- | --- | --- | --- | --- | --- |
| ollama serve | **336** | 503 | 15:53:49 | 1 | ~32s after boot | **held** (not near login) |
| celery parent | **339** | 503 | 15:53:49 | 1 | ~32s after boot | **held** |
| celery children | 582 / 585 | 503 | 15:54:07 / 15:54:09 | - | near boot | **held** |

- `launchctl print system/com.local-agent.ollama` and `system/com.local-agent.celery-worker`: username=rhineduran, group=staff, state=running, pid 336/339, runs=1, never exited. Not uid 0.
- curl `http://127.0.0.1:11434/api/tags` -> **200**.
- gui/503: those labels present only as **disabled**; no live gui jobs for them.
- `Ollama.app` **not** running (`pgrep` empty).
- Last celery ready line still **15:54:18** (no post-login restart).

**PASS:** same pids/start times as pre-login; starts track cold boot, not GUI login. Had pids changed to new processes whose `lstart` tracked login, that would have been a real failure.

## Leftover

`/etc/kcpassword` still present (`-rw------- root wheel`, dated Sep 13 2022), inert without `autoLoginUser`. Cleanup deferred: `sudo rm -f /etc/kcpassword` (needs interactive sudo later).

## Observe commands (no kickstart / no gui domain load)

SSH from DuranGamingPC: `ssh -i A:\Users\rhine\.ssh\workstation_to_mac ... rhineduran@10.90.90.2`.
Checks: `sysctl kern.boottime`, `stat -f %Su /dev/console`, `who`/`last -2`, `ps -p 336,339,582,585`, `launchctl print system/com.local-agent.*`, curl tags, gui/503 disabled grep, celery stderr ready line.