# 2026-09-03o — live verification: Redis secondary ACL restart hook

Live bounce of `local-agent-phase1-redis` on DuranGamingPC. Did **not** re-run
`Add-Phase1SecondaryWorkerCredential.ps1`. Did **not** kickstart/kill/restart
the Mac Celery LaunchAgent. Did **not** reboot Windows, logoff, lock, or stop
the logged-in session. Did **not** restart the Docker engine. Redis left
running and healthy.

Letter `n` was already taken (`2026-09-03n_farm_status_dashboard.md`). `o` was
free at write time.

All times America/New_York (UTC-4) unless labeled. Mac wall clock was ~6s
behind Windows during this run (Windows 13:43:47.037 vs Mac `date`
13:43:41 -0400).

## Claims

| Claim | Verdict |
| --- | --- |
| 1. Session-0 / Docker Desktop unattended start (no login) | **UNTESTED** (explicit). Not a pass. |
| 2. After live Redis bounce, hook restores `mac_worker` (actual ACL, not just wrapper log) | **PASS** |
| 3. Mac Celery reconnects on its own (no manual Mac restart) | **PASS** |
| 4. Real ET timings T0 / T_broker / T_worker | Recorded below |

## Claim 1 — Session-0 unattended start: UNTESTED

A real reboot is not safe while Rhine is logged in. This session did not reboot,
did not lock the session, and did not restart Docker Desktop / the engine.

Inspect-only evidence (does **not** prove Session-0):

- `LastBootUpTime` = 2026-09-01 20:30:44 ET
- Earliest `Docker Desktop` / `com.docker.backend` process start = 2026-09-01 23:08:39 ET (**157.9 minutes after boot**, login-timed)
- Docker Desktop `settings-store.json`: `AutoStart=true`
- `HKCU:\...\Run` has `Docker Desktop` (user-logon start, not Session-0)
- Windows service `com.docker.service` = Stopped / StartType=Manual
- Redis container before this bounce: StartedAt 2026-09-03 03:56:29 ET (from the 03:55 AM hook install), far after boot

`docs/FARM_HEALTH_RUNBOOK.md` already says reboot persistence is not confirmed.
This run does not change that.

Safe test (Rhine present, planned): auto-login **off**, reboot, wait at the lock
screen (do not log in, do not open Docker Desktop). After unlock, compare
container `StartedAt` vs `LastBootUpTime` vs Docker engine process start. If
`StartedAt` is shortly after boot and before unlock, Session-0/unattended start
is confirmed. If Docker only appears after unlock, it is login-item start.
Do not treat this afternoon's `docker restart` as that test — it is a
container bounce from an already-logged-in session.

## Live bounce (claims 2–4)

### Baseline (before bounce)

- 13:37:47 ET: `local-agent-phase1-redis` Up 10 hours (healthy), image
  `redis:7-alpine`, entrypoint `sh /usr/local/bin/redis-with-acl-restore.sh`,
  RestartCount=0, StartedAt 2026-09-03T07:56:29Z = 03:56:29 ET
- 13:38:29–13:38:42 ET: default `PING` = **PONG**. `ACL USERS` = `default`,
  `mac_worker`. `ACL GETUSER mac_worker` (password **redacted**): flags `on`;
  commands `+@all -flushall -flushdb -config -shutdown -acl -debug -cluster
  -replicaof`; keys `~*`; channels `&*`
- 13:38:48–13:38:54 ET: `farm_health` **ok**. `celery@Louises-MBP` responding,
  latency ~2.3–3.3s, expected tasks registered
- 13:38:31 ET Mac LaunchAgent observe-only: `com.local-agent.celery-worker`
  pid **3895**, state=running, runs=11, last exit code=1, KeepAlive + RunAtLoad.
  SSH `rhineduran@10.90.90.2` (key `workstation_to_mac`, IdentitiesOnly,
  BatchMode)

Gitignored credential files present (names/sizes only): `.env` 454,
`.env.mac_worker.generated` 378, `runtime/redis-acl/.env.mac_worker.generated` 378.

### T0 — bounce

Issued `docker restart local-agent-phase1-redis`. The remote-shell wrapper
dropped mid-command; the host still applied the restart (Redis log SIGTERM).

- **T0** = **2026-09-03 13:39:09.402 ET** — Redis log
  `Received SIGTERM scheduling shutdown`
- Container `StartedAt` = 2026-09-03T17:39:10.242613187Z =
  **13:39:10.242 ET**. RestartCount still 0 (manual restart; not the
  unless-stopped crash counter)

### T_broker — default user reachable + hook ran

- Redis `Ready to accept connections tcp` = **13:39:10.613 ET**
- Wrapper (after it waits for default PONG):
  `redis-acl-restore: restored ACL user 'mac_worker'`
  `redis-acl-restore: restored 1 secondary ACL user(s)`
  at **13:39:10.773 ET**
- **T_broker** = **13:39:10.773 ET** (default PING already PONG; hook completed).
  Delta T0→T_broker ≈ **1.37s**
- This session's first re-observed `Health=healthy` + default PING PONG after
  the tool disconnect: 13:41:17 ET. That is **not** first-healthy; Docker
  only retains the last 5 healthcheck rows (all exit=0 starting 13:41:51 ET)

### Claim 2 — actual ACL on the running instance: PASS

Checked on the post-bounce instance (13:41:17, 13:42:52, 13:43:58 ET):

- default `PING` = **PONG**
- `ACL USERS` = `default`, **`mac_worker`**
- `ACL GETUSER mac_worker` (password redacted): flags `on`;
  `+@all -flushall -flushdb -config -shutdown -acl -debug -cluster -replicaof`;
  keys `~*`; channels `&*`

This is the running Redis ACL, not only the wrapper log. Left Redis
`Up … (healthy)` at 13:43:58 ET.

### Claim 3 — Mac reconnect without manual restart: PASS

Did not `launchctl kickstart`, kill, or restart Celery.

- After bounce, LaunchAgent still pid **3895**, runs still **11**, last exit
  still 1, state=running (same process as baseline)
- Mac `worker.stderr.log` (broker URLs redacted):
  - 13:39:03.932 Mac ET: `Connection to broker lost. Trying to re-establish…`
  - 13:39:03.972 Mac ET: `Cannot connect … Connection closed by server.`
    `Trying again in 2.00 seconds... (1/100)`
  - 13:39:06.174 Mac ET: `Connected to redis://***:***@10.90.90.1:6379/0`
  - 13:39:07.266 Mac ET: `mingle: all alone`
- No later disconnect/connect lines after that. In-process Celery retry, not
  a LaunchAgent recycle

Mac timestamps sit ~6s behind Windows, so Mac 13:39:03.932 ≈ Windows T0
13:39:09.4, and Mac Connected 13:39:06.174 ≈ **Windows 13:39:12 ET**.

### T_worker — inspect.ping

- **T_worker (Mac Connected log)** ≈ **13:39:12 ET Windows** / 13:39:06.174 Mac.
  Delta T0→T_worker ≈ **3s**; T_broker→T_worker ≈ **1s**
- **T_worker (this session's first `farm_health` inspect.ping)**:
  **13:43:10.189 ET** — `workers responding: yes`, `celery@Louises-MBP`,
  registered-task status ok, latency 2445.8 ms. The poll started late because
  the host tool connection dropped from ~13:39:11 to ~13:41:17 and again
  briefly after; the worker was already connected per Mac logs

## Leftover

- Session-0 / reboot persistence still unconfirmed. Use the safe test above.
- Keep `.env.mac_worker.generated`. Do not re-run Add-Phase1 to survive a
  Redis bounce.
