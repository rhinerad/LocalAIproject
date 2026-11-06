# 2026-09-03az — Farm Redis via `\local-agent-wsl-docker-boot`: investigation and migration plan (not executed)

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: plan only.** Did not stop, restart, or recreate `local-agent-phase1-redis`. Did not copy or delete `worker_farm_redis-data`. Did not change Docker Desktop `settings-store.json`, `HKCU\...\Run`, `com.docker.service`, compose.yaml, `.env`, ACL files, or `\local-agent-wsl-docker-boot`. Live Redis left running on Docker Desktop.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03az**. Boot proof this session: `2026-09-03au` (watchdog ALIVE) / `2026-09-03at` (unattended keep-alive). ACL lockdown: `2026-09-03al` / `2026-09-03aj`. ACL restore hook: `2026-09-03l` / `2026-09-03o`. Original Session-0 inspect: `2026-09-03o` claim 1 UNTESTED.

## Verdict in one paragraph

`Ubuntu-24.04` is **not** Docker Desktop's engine. It is a separate WSL2 distro with its own Docker CE 29.7.2. Farm Redis already runs on a **second** engine inside the `docker-desktop` distro, published onto Windows `127.0.0.1:6379` by `com.docker.backend.exe` after interactive logon. Docker Desktop cannot be pointed at `Ubuntu-24.04` as a replacement engine; WSL integration would do the opposite (Ubuntu CLI → Desktop daemon). The migration that matches the goal is: copy the existing Redis volume onto Ubuntu Docker CE, start the **same** compose project there, prove Windows `127.0.0.1:6379` still answers, then turn **off** Desktop AutoStart / HKCU Run so there is one Redis, not two. Localhost publishing is the hard, unproven step — WSL is NAT (`172.29.159.194/20`), not mirrored, and Desktop is what currently owns the Windows loopback port.

Do not cut over until Rhine approves, and not until a spare-port localhost probe from Windows into Ubuntu Docker CE succeeds.

## 1. Are the WSL distros the same?

Live `wsl -l -v` (this session, after the 20:59:02 boot):

| Distro | State | Role |
| --- | --- | --- |
| `Ubuntu-24.04` (default) | Running | `\local-agent-wsl-docker-boot` target. Docker **CE** 29.7.2, `Name=DuranGamingPC`, OS=`Ubuntu 24.04.4 LTS`, context `unix:///var/run/docker.sock`, `/usr/bin/docker` from apt (`docker-ce` 5:29.7.2). systemd docker enabled+active. Only container: `wsl-boot-probe`. No `worker_farm_redis-data`. |
| `docker-desktop` | Running | Docker Desktop 4.88.1 engine. `Name=docker-desktop`, OS=`Docker Desktop`, Windows CLI context `desktop-linux` → `npipe:////./pipe/dockerDesktopLinuxEngine`. Container `local-agent-phase1-redis`. Volume `worker_farm_redis-data`. |
| `salad-enterprise-linux` | Stopped | Unrelated. |

No `docker-desktop-data` distro name (4.88 stores engine data under `A:\Users\rhine\AppData\Local\Docker\wsl\main`). Same WSL kernel (`6.6.87.2-microsoft-standard-WSL2`), **separate** `/var/lib/docker`. Ubuntu has `/mnt/wsl/docker-desktop/` (Desktop CLI tools + shared-sockets) but that is a mount, not the daemon Ubuntu uses. Ubuntu `docker context ls` is `default` → `/var/run/docker.sock` created 20:59 (boot), not Desktop's socket.

**Implication:** Redis cannot "just run there" as the current container. It is a different engine, different volume store, different port publisher. Enabling Desktop "WSL integration" on Ubuntu-24.04 would replace/conflict with the CE `dockerd` the boot task already starts — that is the wrong direction.

Docker Desktop has no supported setting to use `Ubuntu-24.04` as its Linux engine. `settings-store.json` tonight only has eight keys (`AutoStart`, onboarding, AI, snapshotter, license). No `integratedWslDistros`. `Use the WSL 2 based engine` still means the `docker-desktop` distro.

## 2. Can Docker Desktop stay off at login, with Ubuntu bringing up the same Redis?

Yes, as a **move**, not a reconfiguration of Desktop's engine.

Desktop start path tonight (same class as `2026-09-03o`):

- `settings-store.json` `AutoStart=true`
- `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` `Docker Desktop` = `C:\Program Files\Docker\Docker\Docker Desktop.exe`
- Service `com.docker.service` = **Stopped / Manual** (not Session-0)
- Processes `Docker Desktop` / `com.docker.backend` StartTime **21:05:35–21:05:59** (explorer 21:05:16; LastBootUpTime 20:59:02)
- Redis `StartedAt` **21:08:05** (~3 min after logon, ~9 min after boot)

Windows `127.0.0.1:6379` Listen owner: `com.docker.backend.exe`. `10.90.90.1:6379` Listen owner: `python` tunnel-relay (logon task, out of this Redis cutover). No `netsh portproxy`. `.wslconfig` is NAT (`memory=24700MB` only; no `networkingMode=mirrored`).

Turning AutoStart + HKCU Run off **will** stop Redis from appearing after logon unless Ubuntu Docker CE is already publishing it. That is intended, after the cutover is proven. Do not flip those bits first.

"Same compose, same volumes, same port bindings" maps as:

| Piece | Same file? | Same bytes/effect? |
| --- | --- | --- |
| `compose.yaml` | yes, run it from Ubuntu | command/entrypoint/healthcheck/ACL bind mounts unchanged |
| Named volume `redis-data` → `worker_farm_redis-data` | same **name** after `volume create` | **not** the same bytes until an explicit copy from Desktop's `/var/lib/docker/volumes/worker_farm_redis-data/_data` |
| `"127.0.0.1:6379:6379"` in YAML | yes | **not** the same Windows effect: Desktop's backend binds the Windows loopback; CE's docker-proxy binds inside the Ubuntu netns. WSL localhost relay is unproven for a guest `127.0.0.1` publish on this NAT setup. |
| Image `redis:7-alpine` | yes | not present in Ubuntu (only `alpine:3.21`). Pull **before** the cutover reboot. |
| Bind mounts `./redis-with-acl-restore.sh` and `./runtime/redis-acl` | same NTFS files via `/mnt/a/...` | boot task is RunAs `rhine` S4U; Linux default uid in Ubuntu is **0**. drvfs uses the Windows token of the `wsl.exe` launcher, so `rhine:(R,W)` on the secret files should still be readable. Confirm during the probe. |

Goal constraint: **one** Redis. Never `compose up` on Ubuntu while Desktop still publishes `127.0.0.1:6379`.

## 3. State that must survive

### Redis data volume

Inspect-only `docker exec` / `docker volume inspect` (no restart):

- Volume `worker_farm_redis-data`, created 2026-08-29, driver local, mountpoint `/var/lib/docker/volumes/worker_farm_redis-data/_data` **inside docker-desktop**.
- `/data/dump.rdb` (~79 KiB)
- `/data/appendonlydir/`: Redis 7 multi-part AOF (`appendonly.aof.3.base.rdb` ~20 MiB, `appendonly.aof.3.incr.aof` ~32 MiB, `appendonly.aof.manifest`). Matches compose `--appendonly yes --appendfsync everysec`.

Copy must take the **entire** `/data` tree, preferably after a **stop** of the Desktop container (not a live tar of a growing incr AOF). Keep the Desktop volume until Ubuntu has passed a delayed-login reboot. Do not `docker volume rm`.

### ACL / secrets (do not rotate)

`2026-09-03al` lockdown, names only:

- `worker_farm/.env` (454 B) — `REDIS_PASSWORD`, loopback `FARM_BROKER_URL` / `FARM_RESULT_BACKEND`, AES key
- `worker_farm/.env.mac_worker.generated` (378 B)
- `runtime/redis-acl/.env.mac_worker.generated` (378 B, staged copy)

icacls on all three: `DURANGAMINGPC\rhine:(R,W)` + `NT AUTHORITY\SYSTEM:(R,W)` only. Wrapper `redis-with-acl-restore.sh` reapplies `mac_worker` on every container start (`2026-09-03l` / `o`). **Do not** run `Add-Phase1SecondaryWorkerCredential.ps1` during migration (it generates a new password and locks out the Mac). `Restore-Phase1SecondaryWorkerCredentials.ps1 -SyncOnly` is the staging path; full restore uses Windows `docker exec` today.

### `START_PHASE1_BROKER.ps1` (and siblings) assume Desktop

Hard assumptions to change **in the same cutover**, not after:

- PATH prepend `C:\Program Files\Docker\Docker\resources\bin` for `docker-credential-desktop` (needed for Desktop pulls; Ubuntu CE pulls `redis:7-alpine` without it)
- `docker.exe` default `C:\Program Files\Docker\Docker\resources\bin\docker.exe`
- Throws "Docker Desktop is not available" / "Open Docker Desktop, wait for Engine running"
- `docker version --format '{{.Server.Version}}'` 15s probe against the **Desktop** named pipe
- `docker compose --env-file .env up -d redis` from a Windows cwd (Desktop bind-mounts `A:\` as `/run/desktop/mnt/host/a/...`)

Also Desktop-flavored:

- `doctor.py` `docker_path()` / `engine_status()` — same `docker.exe` + `docker version`; ready=false if Desktop is off even if Ubuntu Redis is up. `broker_reachable()` is already TCP `127.0.0.1:6379` (keep).
- `Restore-Phase1SecondaryWorkerCredentials.ps1` non-SyncOnly: `docker.exe` + `docker exec local-agent-phase1-redis redis-cli ACL SETUSER ...`
- `RUN_PHASE1_DOCTOR.ps1`, README "wait until Docker Desktop itself shows Engine running", `START_PHASE1_BROKER_VISIBLE.cmd`

Keep: compose `127.0.0.1:6379:6379` (do not widen to `0.0.0.0` without a separate decision), `restart: unless-stopped`, ACL wrapper + `runtime/redis-acl` bind, `.env` password, `FARM_BROKER_URL` host `127.0.0.1` (workstation) and Mac `10.90.90.1` (relay). `celery_app` allowlist is those two hosts; no URL change if loopback still works.

`keep-alive.sh` already `systemctl start/enable docker` and runs `wsl-boot-probe`. Redis compose up would be an **additive** step after `docker info` succeeds, not a replacement of the probe.

### Out of scope but coupled

`\local-agent-tunnel-relay` is still **LogonTrigger / Interactive**. Even with Redis at boot, the Mac (`redis://mac_worker@10.90.90.1:6379/0`) stays dark until rhine logs in, unless relay is migrated separately. Workstation-local clients only need Windows `127.0.0.1:6379`.

## 4. Proposed steps (execute only after approval)

### Phase A — spare-port localhost probe (no farm Redis)

1. On Ubuntu Docker CE, run a throwaway publisher on **16379** (not 6379), e.g. `redis:7-alpine` or `alpine` nc, `-p 127.0.0.1:16379:6379` **or** a known-listen-on-127.0.0.1 case matching compose.
2. From **Windows** (not from inside WSL): `Test-NetConnection 127.0.0.1 -Port 16379`. Also try bind `0.0.0.0:16379` if 127.0.0.1-in-guest fails.
3. Confirm the boot task's root/drvfs can read `runtime/redis-acl/.env.mac_worker.generated` (`icacls` + `wsl -d Ubuntu-24.04 -- cat` should fail closed if ACL broke; do not print contents).
4. Pre-pull `redis:7-alpine` on Ubuntu. Remove the throwaway container/port.

**Gate:** if Windows cannot open Ubuntu-published `127.0.0.1:<port>`, **stop**. Fallbacks (separate decision, not the default): WSL `networkingMode=mirrored` in `.wslconfig` (broad); or a boot-time Windows loopback proxy (same idea as tunnel-relay, bind `127.0.0.1:6379` → Ubuntu NAT `172.29.x.x:6379`); or compose `0.0.0.0:6379` plus Windows firewall (violates the current local-only comment). Do not guess.

### Phase B — code/launcher prep (still no live cutover)

1. Add a small helper used by `START_PHASE1_BROKER.ps1`, `Restore-Phase1SecondaryWorkerCredentials.ps1`, and `doctor.py`: invoke `wsl.exe -d Ubuntu-24.04 --exec docker` (or `wsl ... --cd /mnt/a/.../worker_farm -- docker compose`). Fail clearly if that distro/engine is down.
2. Keep Desktop `docker.exe` as **rollback** path behind an explicit switch (e.g. `-Engine Desktop` or env `FARM_REDIS_ENGINE=desktop|wsl`), default staying Desktop until Phase C succeeds.
3. Extend `keep-alive.sh` (or a sibling script the boot task calls after docker is up) to: `Restore -SyncOnly` equivalent is already on NTFS; then `docker compose --env-file .env up -d redis` from the worker_farm path under `/mnt/a/...`. Do not pull on every boot if the image is present. Do not start Redis if `local-agent-phase1-redis` is already running on this engine.
4. Do **not** enable Docker Desktop WSL integration on Ubuntu-24.04.

### Phase C — maintenance window cutover (one Redis)

1. Confirm Mac/workstation can pause briefly. Record `docker inspect` StartedAt, `ACL USERS` (names only), `farm_health`.
2. `Restore-Phase1SecondaryWorkerCredentials.ps1 -SyncOnly` (no password rotation).
3. **Stop** Desktop Redis (`docker compose --env-file .env stop redis` on Desktop context). Do not `down -v`.
4. Tar `/data` from `worker_farm_redis-data` (Desktop) to a folder **outside** both volume dirs (e.g. `A:\Users\rhine\AppData\Local\local-agent\redis-vol-backup\<timestamp>.tgz`). Verify tar size ≈ AOF+rdb.
5. On Ubuntu: `docker volume create worker_farm_redis-data` (or let compose create it), extract tar into that volume, `docker compose --env-file .env up -d redis` from `/mnt/a/.../worker_farm`.
6. Windows: TCP `127.0.0.1:6379`; default PING PONG; `ACL USERS` includes `mac_worker` (wrapper log + live ACL); `farm_health` from workstation. If relay still up, Mac ping without rotating credentials.
7. Only after that: set Desktop `AutoStart=false` **and** remove HKCU Run `Docker Desktop`. Leave Docker Desktop **installed**. Leave Desktop volume in place.
8. Delayed-login reboot proof (same bar as `2026-09-03au`): auto-logon off, wait ≥3 min at lock screen, then sign in. Pass only if Redis `StartedAt` is shortly after `LastBootUpTime` / boot-task Last Run and **before** explorer, and `127.0.0.1:6379` is not owned by `com.docker.backend.exe`.

### Phase D — cleanup (later)

After a second successful reboot: document persistence in `ARCHITECTURE.md` / `write_handoff_status.py` seed. Optionally quit Docker Desktop on login (already AutoStart off). Do not delete the Desktop volume until Rhine says so.

## 5. What can go wrong

- **Windows 127.0.0.1:6379 dead** after Desktop is down — WSL NAT + guest `127.0.0.1` publish. Workstation broker URLs and tunnel-relay upstream both break. Mitigate with Phase A; rollback Desktop.
- **Two Redis** if Ubuntu compose up while Desktop still holds 6379 — clients keep talking to the old one; Ubuntu copy diverges. Never overlap publishers.
- **AOF torn copy** if tar while Redis is writing. Always `compose stop` first.
- **`mac_worker` missing** if `runtime/redis-acl` unreadable from WSL (ACL/drvfs) or `-SyncOnly` skipped. Wrapper cannot invent the password. Do not run Add-Phase1.
- **Desktop WSL integration** fighting Ubuntu `dockerd` for `/var/run/docker.sock` — boot probe and Redis would flake. Do not enable integration.
- **Image pull at boot** fails (no net yet at PT30S). Pre-pull.
- **doctor / START_PHASE1_BROKER** still probing Desktop — false "engine down" while Redis is up. Change those in Phase B.
- **Port conflict on later Desktop launch** — if someone opens Docker Desktop after cutover, its redis `unless-stopped` may start and steal Windows 6379. After cutover, `compose stop` / remove the Desktop container or disable its restart, without deleting the volume.
- **Mirrored networking** as a panic fix can change all WSL IPs/firewall; treat as a last resort.
- **Relay still logon-only** — Mac stays down until login even if Redis passed Phase C. Do not call that a farm-wide Session-0 pass.

## 6. Rollback (back to today's known-working path)

Today's working path: logon → HKCU Run + AutoStart → Docker Desktop engine → `local-agent-phase1-redis` on `worker_farm_redis-data` → `com.docker.backend` listens `127.0.0.1:6379` → tunnel-relay `10.90.90.1:6379` → Mac.

Rollback:

1. In Ubuntu: `docker compose --env-file .env stop redis` (or `wsl -d Ubuntu-24.04 -- docker stop local-agent-phase1-redis`). Do not `down -v` on Ubuntu if you might retry.
2. Restore Desktop AutoStart=`true` and HKCU Run value if they were removed.
3. Start Docker Desktop, wait Engine running.
4. From `worker_farm` on Windows: `docker compose --env-file .env up -d redis` (Desktop context). Volume `worker_farm_redis-data` is still the pre-cutover data if Ubuntu never wrote back into it. If the cutover had been serving traffic, copy Ubuntu `/data` back onto the Desktop volume **before** starting Desktop Redis, or accept data loss since the last Desktop stop.
5. Confirm Windows `127.0.0.1:6379` owner is again `com.docker.backend.exe`, default PING, `mac_worker` present, `farm_health`.
6. Revert `START_PHASE1_BROKER.ps1` / `doctor.py` / `keep-alive.sh` to the Desktop default (or set `FARM_REDIS_ENGINE=desktop`). Leave `\local-agent-wsl-docker-boot` running; it only keeps Ubuntu Docker CE + probe and must not start Redis after rollback.

If Desktop volume was deleted in error: restore from the Phase C timestamped tarball.

## 7. What this session actually did

Read-only: `wsl -l -v`, both `docker info`/`ps`/`volume`, `docker inspect`/`exec ls` on Redis, `settings-store.json`, HKCU Run, `com.docker.service`, `.wslconfig`, Ubuntu `wsl.conf`/`dpkg`/`docker context`, listeners on 6379, icacls **names/sizes only**, compose.yaml, START_PHASE1_BROKER.ps1, Restore/doctor/keep-alive/install-docker-ce.sh.

Did not: `compose up/down`, `docker restart`, volume create/rm, settings writes, task changes, Add-Phase1, password print, spare-port probe (that is Phase A, needs approval because it starts a container).
