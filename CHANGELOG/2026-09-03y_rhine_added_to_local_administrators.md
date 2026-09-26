# 2026-09-03y — rhine added to local Administrators (standing privilege change)

Date: 2026-09-03. Host: DuranGamingPC (Windows 11 Home). All times America/New_York (UTC-4).

**This is an account privilege change, not a boot-task footnote.** `DURANGAMINGPC\rhine` is now a local Administrator on this machine going forward. Anyone reading later should treat `rhine` as an admin account, not a standard user.

## What changed

`Add-LocalGroupMember -Group Administrators -Member DURANGAMINGPC\rhine` (equivalent: `net localgroup Administrators DURANGAMINGPC\rhine /add`).

- Caller: elevated `DURANGAMINGPC\tiffa` (`ADMIN=True`). `rhine` was not admin yet, so tiffa UAC was required for this one step.
- Before: Administrators = `Administrator`, `tiffa`.
- After (`net localgroup Administrators`): `Administrator`, `rhine`, `tiffa`.
- SID: `S-1-5-21-3342793278-1091766691-3607590999-1004`.
- Standing: this membership is not scoped to one task and is not reverted in this entry.

Id from `python scripts/next_changelog_id.py` (2026-09-03y). Letters through `x` were already taken today.

## Why

S4U + BootTrigger scheduled tasks cannot be registered with principal `rhine` while `rhine` is a standard user (`0x80070005` from elevated tiffa, from SYSTEM, from XML, and from COM). Admin-as-self S4U already worked (tiffa). Granting local Administrators to `rhine` was the approved remaining lever that does not store a password and does not fall back to a Logon trigger.

## Follow-on that this grant unblocked (not the headline)

After membership landed, `rhine` self-elevated (`USER=DURANGAMINGPC\rhine ADMIN=True`, not tiffa) and registered `\local-agent-wsl-docker-boot`:

- Ready, RunAs `rhine`, LogonType **S4U**, trigger **MSFT_TaskBootTrigger** / At system start up, delay PT30S
- Action: `C:\Program Files\WSL\wsl.exe -d Ubuntu-24.04 --exec /bin/bash /mnt/a/Users/rhine/AppData/Local/local-agent/wsl-boot-probe/keep-alive.sh boot`
- Verified by `Get-ScheduledTask` + `Export-ScheduledTask` + `schtasks /Query /FO LIST /V`, not by create exit code alone

**Not proven at boot.** Delayed-login reboot test is still due: wait ~3 minutes at the lock screen, sign in, compare `heartbeat.log` instance id / `SOURCE=boot` vs `SOURCE=watchdog`. That result is a separate changelog letter.

Farm Redis / Docker Desktop were not migrated. `\local-agent-wsl-docker-logon-watchdog` left in place for the proof test.