# 2026-09-03l — secondary Redis ACL users survive container restart

## What

Secondary Redis ACL users (`mac_worker` and any later `.env.<username>.generated`
credential) were in-memory only and vanished on every Redis container restart.
`compose.yaml` has `restart: unless-stopped`, so Docker can bounce
`local-agent-phase1-redis` without `START_PHASE1_BROKER.ps1`. Re-running
`Add-Phase1SecondaryWorkerCredential.ps1` was the old recovery path, but that
script generates a **new** password each time and would lock out the Mac worker.

Fix: wrap `redis-server` inside the container so the same `--requirepass` flags
still start Redis, then reapply stored secondary ACL users after PONG. No
`--aclfile` (that was deliberately avoided so default-user / requirepass
handling stays unchanged).

## How the hook works

`compose.yaml` sets `entrypoint` to `sh /usr/local/bin/redis-with-acl-restore.sh`
and keeps the existing `redis-server --appendonly yes --appendfsync everysec
--requirepass ${REDIS_PASSWORD} --maxmemory-policy noeviction` command. The
wrapper backgrounds the image's `docker-entrypoint.sh` with those args (so
setpriv / redis-user drop is unchanged), waits for `PING` to `PONG` as the
default user, then `ACL SETUSER` for each `/acl-restore/.env.<username>.generated`
using that file's existing `FARM_BROKER_URL` password and the current grant
(`~*`, `&*`, `nocommands`, `+@all`, then `-flushall -flushdb -config -shutdown
-acl -debug -cluster -replicaof`). It never touches `default`. A bind mount of
`runtime/redis-acl` supplies the files; `START_PHASE1_BROKER.ps1` and
`Add-Phase1SecondaryWorkerCredential.ps1` stage copies there via
`Restore-Phase1SecondaryWorkerCredentials.ps1 -SyncOnly`. Because the wrapper
is the container entrypoint, it also runs on `docker restart`, not only on
`compose up`.

## Files

- `local_agent/worker_farm/redis-with-acl-restore.sh` (new; LF-only)
- `local_agent/worker_farm/Restore-Phase1SecondaryWorkerCredentials.ps1` (new;
  restore / stage only — does not generate passwords)
- `local_agent/worker_farm/compose.yaml` — entrypoint + bind mounts; requirepass
  command flags unchanged (now an argv list so the password stays one argument)
- `local_agent/worker_farm/START_PHASE1_BROKER.ps1` — stages generated files
  before `compose up`
- `local_agent/worker_farm/Add-Phase1SecondaryWorkerCredential.ps1` — header and
  staging updated; still generates a new password on purpose when creating a
  **new** user
- `local_agent/worker_farm/README.md` — operator note not to rotate on restart

Gitignored credential copy used by the hook:
`local_agent/worker_farm/.env.mac_worker.generated` (and the staged copy under
`runtime/redis-acl/`). `.gitignore` already has `.env.*` and `runtime/`.

## Tests (2026-09-03 ~3:55 AM ET, DuranGamingPC)

Did **not** re-run `Add-Phase1SecondaryWorkerCredential.ps1` or
`FixMacWorkerACL.ps1`. Existing `mac_worker` password reused from the Mac
node env (copied to the gitignored generated file; URLs/passwords not printed).

1. Baseline before any recreate: default `PING` = **PONG**; `mac_worker` AUTH
   `PING` = **PONG**.
2. `docker compose --env-file .env up -d redis` recreated the container.
   Wrapper log: restored ACL user mac_worker / restored 1 secondary ACL user(s).
   Health: healthy. default `PING` = **PONG**; `mac_worker` AUTH = **PONG**.
3. `docker restart local-agent-phase1-redis` (the path that used to drop ACLs).
   Waited until healthy (~16s). Wrapper log again restored mac_worker.
   default `PING` = **PONG**; `mac_worker` AUTH = **PONG**.
4. `ACL USERS` = `default`, `mac_worker`. `ACL GETUSER mac_worker` (password
   redacted): flags `on`; keys `~*`; channels `&*`; commands
   `+@all -flushall -flushdb -config -shutdown -acl -debug -cluster -replicaof`.

## Leftover risk

- The workstation **must keep** `.env.<username>.generated`. Deleting it (the
  old cleanup note) would leave the wrapper with nothing to restore; the
  next restart would drop that user until the file is put back. Do not
  re-generate.
- `runtime/redis-acl` is a staged copy. `START_PHASE1_BROKER.ps1` refreshes it
  via Restore `-SyncOnly` before compose up. A credential file added by
  hand while the container is already running is picked up on the next
  container start, or immediately via
  `Restore-Phase1SecondaryWorkerCredentials.ps1` (no `-SyncOnly`).
- A live Celery worker may drop its broker connection across `docker restart`
  and needs its own reconnect; AUTH after restart is the bar that was failing
  before.
