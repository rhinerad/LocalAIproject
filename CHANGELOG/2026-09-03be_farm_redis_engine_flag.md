# 2026-09-03be — FARM_REDIS_ENGINE=desktop|wsl on farm Redis launchers (default desktop)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result:** Phase B of `2026-09-03az` wired. Default behavior is still Docker Desktop. Live `local-agent-phase1-redis` (`4a2fc7893796`), its volume, and Docker Desktop AutoStart were not changed. `keep-alive.sh` was not taught to `compose up` Redis (that is Phase C).

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03be**. Phase A localhost gate: `2026-09-03ba`. Plan: `2026-09-03az`.

## Flag

`FARM_REDIS_ENGINE=desktop|wsl` (case-insensitive). Unset/empty = **desktop**. Also `-Engine desktop|wsl` on the two PowerShell scripts. Invalid values throw / doctor reports `ready: False`.

Shared helper: `local_agent/worker_farm/Resolve-FarmRedisEngine.ps1` (dot-sourced). Desktop: Windows `docker.exe` (same credential-helper PATH prepend as before). wsl: `wsl.exe -d Ubuntu-24.04 --cd <worker_farm> -e /usr/bin/docker`.

Wired:

- `START_PHASE1_BROKER.ps1` — pins `$env:FARM_REDIS_ENGINE` so Restore inherits it; Desktop probe/compose path unchanged
- `Restore-Phase1SecondaryWorkerCredentials.ps1` — `-SyncOnly` still does not talk to Docker; `docker exec` ACL SETUSER uses the selected engine
- `doctor.py` — `redis_engine()`, `docker_argv()`, `engine_status()["engine"]`

Not wired (still Desktop `docker.exe` only): `Add-Phase1SecondaryWorkerCredential.ps1`. That script generates new passwords; it is not the restart path.

## Verification (default unchanged)

- `Resolve-FarmRedisEngine.ps1 -Probe` PASS
- Farm venv unittest: doctor engine tests + `test_phase1_secret_acl` OK (8 tests)
- `python -m local_agent.worker_farm.doctor` (env unset): `docker: {engine: desktop, ready: True, server_version: 29.7.2}`, loopback reachable, exit 0
- `FARM_REDIS_ENGINE=wsl` doctor (probe only, no compose): `engine: wsl`, Ubuntu CE `29.7.2`, exit 0
- Ubuntu image `redis:7-alpine` already cached from Phase A (`sha256:ff02b58f971e…`); no extra pull needed
- Farm Redis still `4a2fc7893796` Up healthy `127.0.0.1:6379`. Ubuntu `docker ps` only `wsl-boot-probe`. `settings-store.json` AutoStart still true

Did not run `START_PHASE1_BROKER.ps1` (that would `compose up` the live broker). Did not run Restore without `-SyncOnly`.

## Next

Phase C maintenance window in `2026-09-03az` still needs an explicit go: stop Desktop Redis, copy volume, `FARM_REDIS_ENGINE=wsl` compose up, then disable AutoStart. Do not set the env var in production until then.
