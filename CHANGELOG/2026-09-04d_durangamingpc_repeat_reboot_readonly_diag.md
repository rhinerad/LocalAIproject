# 2026-09-04d — DuranGamingPC repeat-reboot / disconnected-status read-only diagnosis

Date: 2026-09-04. Host: DuranGamingPC. All times America/New_York (UTC-4). Read-only: no compose up/down, no task changes, no Register-ScheduledTask, no service start/stop, no GPU work.

Id from `python scripts/next_changelog_id.py --date 2026-09-04` immediately before write: **2026-09-04d**.

Prompt: farm dashboard/status keeps reporting DuranGamingPC disconnected after sign-in; sixth reboot. Leading theory: `enforce-lockscreen-wait.flag` (documented one-shot in `2026-09-03at`/`au`) stuck and firing on every reboot.

**Verdict (findings only, no fix):** The lockscreen-wait flag is **not** stuck on disk now. It **did** fire on this boot (re-planted for Phase D, then deleted at T+180s). There has been **no sixth OS restart today** — calendar 2026-09-04 has a single Kernel-General 12 at 01:24:38. Live farm connectivity is **ok**. The LAN dashboard process on :8765 is **not running**, so a phone/browser dashboard would look disconnected even while `farm_status.json` / `farm_health --json` are healthy.

## Clock

- Snapshot: **2026-09-04 12:14:39** (elapsed **39002s** ≈ 10.8h after boot).
- Windows `LastBootUpTime`: **2026-09-04 01:24:37.500**.
- Kernel-General 12: 01:24:38. EventLog 6005/6009: 01:24:49. Event 1074: **01:23:26** `shutdown.exe` restart on behalf of `DuranGamingPC\rhine`, comment: wait 3 minutes at lock screen / Phase D second-boot Redis persistence proof.
- explorer session 1 start: **01:59:08** (+2070s). Interactive logon for this boot, not a later reboot.
- `HiberbootEnabled` not re-queried this pass; prior `2026-09-03au`/`04a` had `HiberbootEnabled=0`.

Event 1074 restarts in this proof campaign (six, matching “6th time” as campaign count, not six boots after 01:24):

| When | Initiator | Comment |
| --- | --- | --- |
| 2026-09-03 19:49:45 | StartMenuExperienceHost | unplanned restart |
| 2026-09-03 20:22:34 | shutdown.exe | BootTrigger delayed-login proof |
| 2026-09-03 20:24:42 | StartMenuExperienceHost | unplanned restart |
| 2026-09-03 20:57:54 | shutdown.exe | WSL Docker-at-boot / 03at–au |
| 2026-09-03 23:34:31 | shutdown.exe | WSL Redis cutover / 03bh |
| 2026-09-04 01:23:26 | shutdown.exe | Phase D second boot / 04c |

No 1074 / Kernel-General 12 after 01:24:38. This session is still that boot.

## 1. Scheduled tasks vs this boot

`LastTaskResult` **267009** (`0x00041301`, `SCHED_S_TASK_RUNNING`) on the three long-running tasks is the keep-alive still running, not a failed exit (same as `2026-09-03au`).

| Task | State | LastRunTime | vs LastBootUpTime | LastTaskResult | Principal | Trigger |
| --- | --- | --- | --- | --- | --- | --- |
| `\local-agent-tunnel-relay` | Running | 01:59:08 | **+2070s** (with explorer) | 267009 | Interactive / rhine | `MSFT_TaskLogonTrigger` |
| `\local-agent-wsl-docker-boot` | Running | 01:25:20 | **+42s** (PT30S) | 267009 | **S4U** / rhine | `MSFT_TaskBootTrigger` Delay=PT30S |
| `\local-agent-farm-status-daemon` | Running | 01:59:08 | **+2070s** (with explorer) | 267009 | Interactive / rhine | `MSFT_TaskLogonTrigger` |

Also observed (not requested): `\local-agent-wsl-docker-logon-watchdog` Ready, Last Run 01:59:08, Result 0, Interactive LogonTrigger. No `boot-proof-once` scheduled task — that script is launched from `keep-alive.sh` only when the lockscreen flag file exists.

Expected gap (unchanged from `2026-09-04a`): tunnel-relay and farm-status-daemon are logon tasks. They stay dark from boot until interactive sign-in. This boot that was **01:59:08**, 34 minutes after boot, because sign-in was late (lockscreen bounce only covers 180s).

## 2. WSL / Ubuntu Redis

`wsl -l -v`:

- **Ubuntu-24.04 Running** v2 (default).
- `docker-desktop` **Stopped**.
- `salad-enterprise-linux` Stopped.

`wsl -d Ubuntu-24.04 -- docker ps`:

- `local-agent-phase1-redis` **Up 11 hours (healthy)** `127.0.0.1:6379->6379/tcp` `redis:7-alpine`.
- `wsl-boot-probe` Up 11 hours `alpine:3.21`.

Inspect: Status=running Health=**healthy** StartedAt=**2026-09-04T05:25:45.041762933Z** (01:25:45 local) — after LastBootUpTime, before explorer. Same StartedAt as `2026-09-04c`.

## 3. Who owns 127.0.0.1:6379

Listen **127.0.0.1:6379** = **wslrelay** pid **15448**. Not `com.docker.backend.exe`. Not empty.

Listen **10.90.90.1:6379** = system Python312 pid **17068** `tunnel_relay.py --bind-ip 10.90.90.1` (parent venv wrapper 16440). Established peers from `10.90.90.2` (Mac) on that listen. Loopback clients: farm_status_daemon python 2752 and the relay itself.

## 4. Flags — lockscreen-wait theory

Probe dir: `A:\Users\rhine\AppData\Local\local-agent\wsl-boot-probe`.

| Flag | On disk now? | Notes |
| --- | --- | --- |
| `redis-cutover-proof.flag` | **MISSING** | Consumed (cutover recorder). |
| `redis-on-wsl.flag` | **EXISTS** | Content `phase-c-2026-09-03`. Created 2026-09-03 23:33:34. Persistent by design (keep-alive may `docker start` Ubuntu redis). |
| `enforce-lockscreen-wait.flag` | **MISSING** | Not present at 12:13. |
| `changelog-written.flag` | EXISTS | Content **`2026-09-03at`** (21:03:38). Later boots skip a new watchdog letter. |
| `phase-d-second-boot.flag` | EXISTS | Leftover `phase-d-second-boot` from 01:23:26. |

`2026-09-03at`/`au` documented the original one-shot: flag deleted after 180s, later boots not bounced. That deletion happened. The flag was **re-planted** for later proofs (`2026-09-03bg` step 6; Phase D `redis-cutover-pending.txt` still lists `enforce-lockscreen-wait.flag,redis-cutover-proof.flag,redis-on-wsl.flag,phase-d-second-boot.flag`).

This boot **did** bounce: `reboot-proof.log` `boot-proof-once start` 01:25:43, `LastBootUpTime=2026-09-04 01:24:37.500`, wait loop logoffs=0 until 01:27:41 `window elapsed` then `Remove-Item` of the flag. Verdict in that log is FAIL (`SOURCE=boot heartbeats too short`) + `changelog already written` — not a new letter (04c is the Redis Phase D PASS). After 01:27:41 the flag is gone; `keep-alive.sh` and `watchdog.sh` only logoff/launch the enforcer when the file exists.

**Theory result:** not stuck now; not the cause of a repeating reboot loop after this boot. It **was** reused beyond the original at/au one-shot (Phase C + Phase D). `redis-cutover-pending.txt` still *names* the flag; the file is not there.

## 5. `farm_health --json` (workstation, farm venv, repo root)

Must be run from the handoff tree root (`-m local_agent.worker_farm.farm_health`). From another cwd: `ModuleNotFoundError: No module named 'local_agent'`. Direct `farm_health.py` fails on relative import.

Live (cwd repo root, 12:16:04, exit 0):

```json
{
  "broker_reachable": true,
  "checked_at": "2026-09-04T16:16:04.534663+00:00",
  "error": null,
  "latency_ms": 5325.4,
  "missing_expected_tasks": [],
  "status": "ok",
  "workers": ["celery@Louises-MBP"],
  "workers_responding": true
}
```

`registered_check.status=ok`. Registered on `celery@Louises-MBP`: `connectivity_probe`, `judge_transcript`, `summarize_conversation`, `embed_chunks`, plus `distill_export`. `farm_status.json` at 12:17:17: `status=ok`, `workers_responding=true`, `latency_ms=2128.5`, age ~seconds (daemon writing). Daemon python 2752 since 01:59:15.

`farm_status_daemon.log` current lines: broker yes, workers yes, `celery@Louises-MBP`. Last `FARM_STATUS_RECOVERED` in the file is historical (including a 127.0.0.1:6379 WinError 10053 blip then recover). No live outage at snapshot.

`.env` `FARM_BROKER_URL` host is `127.0.0.1:6379` (password not copied here). User-env `FARM_REDIS_ENGINE=wsl`. Mac path remains hub `10.90.90.1:6379` via relay.

## 6. WireGuard hub

- Adapter `hub`: **Up**, description WireGuard Tunnel, ifIndex 16.
- Address **`10.90.90.1/28` Preferred** IPv4.
- Service `WireGuardTunnel$hub`: **Running** / Automatic.
- `wg.exe show`: `hub: Permission denied` without elevation (same as prior inspects). Interface/IP assignment does not need that.

LAN Ethernet Up `192.168.50.208/24`.

## Dashboard vs “disconnected”

`netstat` **no listener on :8765**. No dashboard process. No dashboard scheduled task (only `\local-agent-farm-status-daemon`). `runtime/farm_dashboard.out.log` still `http://192.168.50.208:8765/` from an earlier start; `farm_dashboard.err.log` last write **2026-09-03 16:11** (phone `192.168.50.80` GET `/api/dashboard` 200). Dashboard is not a logon task, so it does not come back after these reboots.

If the operator is looking at the LAN page, it will fail to load / look disconnected even though:

- hub 10.90.90.1/28 is up,
- Ubuntu redis is healthy,
- 127.0.0.1:6379 is wslrelay,
- relay is listening and has live `10.90.90.2` sessions (capture 02:01:56 relaying; netstat Established still present at 12:14),
- `farm_health` / `farm_status.json` are `ok` with `celery@Louises-MBP`.

## Not done

No fixes. Did not start the dashboard, did not `Start-ScheduledTask`, did not delete leftover `phase-d-second-boot.flag` / `changelog-written.flag` / `redis-cutover-pending.txt`, did not register a boot tunnel-relay S4U task.
