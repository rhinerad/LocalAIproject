# 2026-09-03m — operator warning: do not rotate secondary Redis ACL on restart

Docs/comments only; Redis wrapper from `2026-09-03l` unchanged.

The restart-hook writeup already exists as `CHANGELOG/2026-09-03l_secondary_redis_acl_restore_on_restart.md` (next unused letter at the time of that fix was `l`). This entry is the follow-up so the "do not re-run Add-Phase1" gotcha is visible between sessions.

## What

- `local_agent/worker_farm/Add-Phase1SecondaryWorkerCredential.ps1`: comment at the top of the script now leads with WARNING — every run mints a new password and breaks the Mac's stored `mac_worker` credential. Restore path and keep-the-generated-file note are in that same header.
- `docs/FARM_HEALTH_RUNBOOK.md`: new "Redis secondary ACL after restart" section next to the other operational traps.

## Why

Re-running Add-Phase1 looks like the recovery for a bounced broker, but it rotates the password. The Mac keeps the old one. The container already reapplies the stored user via `redis-with-acl-restore.sh`.
