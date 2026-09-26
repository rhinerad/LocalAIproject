# 2026-09-03bg — WSL Redis Phase C cutover (pre-reboot): Ubuntu CE serving farm Redis

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result:** Steps 1–6 of Phase C (`2026-09-03az`) completed. Farm Redis is on Ubuntu-24.04 Docker CE. Desktop Redis left **exited**, volume **not** deleted. Delayed-login reboot proof is the next boot (`redis-cutover-proof.flag` + lock-screen bounce).

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03bg**. Launchers: `2026-09-03be`. Phase A: `2026-09-03ba`.

## Steps

1. **ACL sync — PASS.** `Restore-Phase1SecondaryWorkerCredentials.ps1 -SyncOnly`. icacls still `DURANGAMINGPC\rhine:(R,W)` + `NT AUTHORITY\SYSTEM:(R,W)` only on `.env`, `.env.mac_worker.generated`, `runtime/redis-acl/.env.mac_worker.generated`. Ubuntu CE read those files (sizes 454 / 378 / 378); contents not printed.
2. **Stop Desktop Redis — PASS.** `docker compose --env-file .env stop redis` (not `down -v`). Container `4a2fc7893796` Status=exited (0). Volume `worker_farm_redis-data` remains. Windows `127.0.0.1:6379` released; `10.90.90.1:6379` still tunnel-relay python.
3. **Volume copy after stop — PASS.** `A:\Users\rhine\AppData\Local\local-agent\redis-vol-backup\redis-data-20260903-233012.tgz` (32359047 bytes). Tar listing: `dump.rdb`, `appendonlydir/appendonly.aof.3.base.rdb`, `.incr.aof`, `.manifest`. Desktop redis still exited during tar.
4. **Ubuntu compose up — PASS after one helper fix.** First `START_PHASE1_BROKER.ps1 -Engine wsl` aborted because Compose's "volume already exists" **warning** on stderr became a PowerShell terminating error (`Invoke-FarmDocker` `$ErrorActionPreference=Stop` + `2>&1`). Helper now continues on native-command stderr. Retry: container `6ea76294c9cf` created/started. Compose still uses the pre-seeded `worker_farm_redis-data`. Desktop container still exited.
5. **Verify — PASS (all three).** Health=healthy. PING=PONG. `ACL USERS` = `default` `mac_worker`. Wrapper: `restored ACL user 'mac_worker'`. AOF loaded (base + incr). Windows `127.0.0.1:6379` = **wslrelay** (not `com.docker.backend`). `farm_health` exit 0: `celery@Louises-MBP` workers responding, registered tasks ok. Stale `farm_status.json` during the bounce showed `no_workers`; `farm_status_daemon --once` then `status=ok`, `workers_responding=true`.
6. **Desktop AutoStart off — PASS.** `settings-store.json` AutoStart=false (backup under `wsl-boot-probe\desktop-autostart-backup`). HKCU Run `Docker Desktop` removed (value backed up). Desktop redis `Restart=no` (still present, exited, volume intact). User env `FARM_REDIS_ENGINE=wsl`. Flags: `redis-on-wsl.flag` (keep-alive may `docker start` Ubuntu redis), `redis-cutover-proof.flag`, `enforce-lockscreen-wait.flag`.

Rollback was **not** used. Desktop volume remains until Phase D / a second successful reboot.

## Not yet

Delayed-login reboot: wait ≥3 min at lock screen, then sign in. Pass only if Ubuntu redis `StartedAt` is after `LastBootUpTime` and before explorer, and `127.0.0.1:6379` is still wslrelay. Recorder: `redis-cutover-proof.ps1`.
