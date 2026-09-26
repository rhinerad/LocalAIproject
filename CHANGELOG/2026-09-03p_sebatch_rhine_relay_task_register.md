# 2026-09-03p — SeBatchLogonRight for rhine; tunnel-relay task still not registered

All times America/New_York (UTC-4). No reboot. No logoff. Manual `tunnel_relay.py` listener left running. `farm_status_daemon` left running. Did not change `\local-agent-farm-status-daemon`.

Id from `python scripts/next_changelog_id.py` (2026-09-03p). Letter `o` was already taken.

## SeBatchLogonRight

Granted **Log on as a batch job** to `DURANGAMINGPC\rhine`.

- SID: `S-1-5-21-3342793278-1091766691-3607590999-1004`
- Method: `secedit /export` + INF `secedit /configure /areas USER_RIGHTS` (existing SIDs preserved) and additive `LsaAddAccountRights`
- BEFORE export: `SeBatchLogonRight = *S-1-5-32-544,*S-1-5-32-551,*S-1-5-32-559`
- AFTER export: `SeBatchLogonRight = rhine,*S-1-5-32-544,*S-1-5-32-551,*S-1-5-32-559`
- Query-back: secedit line contains `rhine`; `LsaEnumerateAccountRights` on the SID returns `SeBatchLogonRight`
- `SeDenyBatchLogonRight` was not present
- `gpupdate` not run

Elevated as `DURANGAMINGPC\tiffa` (`is_admin=True`). UAC approved.

## Hung elevated PowerShell

Identified then killed leftover register/UAC shells (tiffa, window title Administrator: Windows PowerShell):

- PID 34708 (started 13:37:22) — `-File .../local_agent/worker_farm/runtime/reg-scratch/register.ps1`; PPID 42704 already gone
- PID 25712 (started 13:44:36) — `-File C:\Users\Public\local-agent-tunnel-relay-reg\register.ps1`; PPID 42040 already gone
- PID 44152 (started 14:37:24) — leftover `probe.ps1` hung on `schtasks /Create /NP`; killed on the later elevated run

## Task `\local-agent-tunnel-relay`

**Not registered.** After the rights grant, every S4U create as rhine returned `Access is denied` / `0x80070005`:

- `schtasks /Create /XML /F`
- `Register-ScheduledTask -Xml`
- `Schedule.Service` COM `RegisterTask` logonType 2 (S4U)
- `Register-ScheduledTask` principal objects S4U
- Same three methods from a temporary `NT AUTHORITY\SYSTEM` helper task (`\la-relay-reg-helper`, created and then unregistered). Helper principal was SYSTEM only to *register*; intended relay principal stayed rhine S4U.

Control probes (immediately unregistered):

- tiffa S4U BootTrigger: **SUCCESS**
- tiffa S4U LogonTrigger: **SUCCESS**
- rhine S4U LogonTrigger or BootTrigger from tiffa: **Access is denied**
- rhine self-register Interactive LogonTrigger: **SUCCESS** (then unregistered; not used for the relay)
- rhine self-register S4U (logon or boot) or Interactive BootTrigger: **Access is denied**

Did **not** switch the relay task to Interactive, Password, or SYSTEM. Spec remains: principal `DURANGAMINGPC\rhine`, LogonType S4U, BootTrigger, RunLevel Limited.

XML/spec artifacts: `C:\Users\Public\local-agent-tunnel-relay-reg\task.xml` (SID UserId, S4U, BootTrigger PT30S, Hidden, Restart 999/PT1M, ExecutionTimeLimit PT0S, action cmd.exe + venv python `-u` `local_agent/worker_farm/relay/tunnel_relay.py --bind-ip 10.90.90.1`).

## Start verification

Not run (`schtasks /Run` / reboot). Task does not exist.

## Live path (unchanged)

- Manual listener still owns `10.90.90.1:6379` Listen: python PID **36984** (tree cmd 43704 → venv python 32408 → 36984). Not stopped.
- Mac Established to `10.90.90.1:6379` at write time: **6**
- `127.0.0.1:6379` Listen remains a separate process (PID 37600); not touched
- `farm_status_daemon` still up: cmd 15684 → python 22564 → python 37500

## Result files

- `C:\Users\Public\local-agent-tunnel-relay-reg\result.txt`
- `local_agent/worker_farm/runtime/relay-task-register-result.txt`

## Verdict

**PARTIAL.** Rights grant + query-back succeeded. Task register failed (S4U Access denied as rhine from tiffa and from SYSTEM). Manual listener is still the live path.
