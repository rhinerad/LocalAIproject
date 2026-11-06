# 2026-09-04a — post-reboot recovery inspection (delayed logon of the 23:35 boot)

Date: 2026-09-04. Host: DuranGamingPC. All times America/New_York (UTC-4). Read-only: no compose up/down, no task changes, no Register-ScheduledTask, no Add-Phase1, no GPU work.

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-04a**.

**This is not a second reboot.** `LastBootUpTime` is still **2026-09-03 23:35:43.500** — the WSL Redis cutover boot already recorded in `2026-09-03bh`. Interactive session 1 / explorer landed **2026-09-04 00:18:03** (+2540s). This entry is the post-sign-in recovery check against `HANDOFF_STATUS.md` §3/§4.

Live state matches the later 03s/03am/03bg/03bh picture, not the stale §3/§4 seeds (those still described Desktop Redis, a missing tunnel-relay task, and unverified farm-status logon). The prompt bar that 127.0.0.1:6379 should still be `com.docker.backend.exe` / Phase C untriggered is **wrong for this boot** — Phase C already cut over in `2026-09-03bg`.

## Clock

- Event 1074: 23:34:31 `shutdown.exe` restart on behalf of `DuranGamingPC\rhine` (comment: wait 3 minutes at lock screen; WSL Redis cutover proof). Kernel-General 12: 23:35:44. `HiberbootEnabled=0`.
- `\local-agent-wsl-docker-boot` Last Run **23:36:27** (+44s, PT30S). State Running, Last Result 267009, LogonType **S4U**, BootTrigger.
- `wsl -l -v`: Ubuntu-24.04 **Running** (v2); `docker-desktop` **Stopped**.
- `docker info` (Ubuntu CE): ServerVersion **29.7.2**, ContainersRunning=2, Driver=overlayfs.
- Heartbeat `EVENT=START SOURCE=boot` 23:36:47 instance `ca3bad22-86b2-4793-9ff6-8ef39415db83`. First `DOCKER=29.7.2 PROBE=true`: **23:36:56**. Same instance still writing `SOURCE=boot` after sign-in (count 391+).
- `wsl-boot-probe` alpine:3.21 running, StartedAt 2026-09-04T03:36:51Z.
- Logon watchdog Last Run **00:18:03**, Result 0. `watchdog.log` **00:18:06** `RESULT=ALIVE` same instance (not `RESTART`). Same delayed-login bar as `2026-09-03au`.

## Farm Redis (Phase C persisted; not Docker Desktop)

- Ubuntu CE `local-agent-phase1-redis` `6ea76294c9cf` status=running StartedAt **2026-09-04T03:36:52.135339577Z** (23:36:52 local) health=healthy. Same container id as `2026-09-03bg`/`bh`. After LastBootUpTime and before explorer.
- Windows `127.0.0.1:6379` Listen owner **wslrelay** pid **4488**. No `com.docker.backend` / Docker Desktop processes. `docker-desktop` distro Stopped.
- Default user `PING=PONG`. `ACL USERS` = `default` `mac_worker`.
- Desktop AutoStart **false**. HKCU Run `Docker Desktop` **absent**. User env `FARM_REDIS_ENGINE=wsl`. `redis-on-wsl.flag` present; cutover-proof flag already consumed (`2026-09-03bh` PASS at T+182s, explorer still null).

## WireGuard hub

Matches `2026-09-03h`: adapter `hub` **Up**; `10.90.90.1/28` Preferred; service `WireGuardTunnel$hub` Running / Automatic.

## `\local-agent-farm-status-daemon` — real logon start now verified

§3 said this was only proven via `Start-ScheduledTask` while already logged on. This cycle: Last Run **00:18:03**, State Running, Last Result 267009, LogonTrigger / InteractiveToken. Matches explorer start and User Profile Service session 1. cmd 14564 → venv 15264 → python 3104 (`-m local_agent.worker_farm.farm_status_daemon`), all created 00:18:03–00:18:07. No `Start-ScheduledTask` this session.

## Tunnel relay — down until interactive logon, then the logon task started it

Boot/S4U `\local-agent-tunnel-relay` is still **not** registered (03h Access Denied). Did not retry `Register-ScheduledTask`.

The **logon/Interactive** fallback from `2026-09-03s` (self-start proven `2026-09-03am`) did fire: Last Run **00:18:03**, State Running, Last Result 267009. `tunnel_relay_task_run.log` START 00:18:04. Listen `10.90.90.1:6379` owned by system Python312 **15260** (`tunnel_relay.py --bind-ip 10.90.90.1`). Capture `relaying` 00:20:48; first Mac `10.90.90.2` 00:21:12. Live: 9 Established from `10.90.90.2`. Expected: dark from boot until rhine logs on; up after that.

## `farm_health --json` (workstation, after Redis + relay up)

```json
{"status":"ok","broker_reachable":true,"workers_responding":true,"workers":["celery@Louises-MBP"],"missing_expected_tasks":[],"latency_ms":2399.9}
```

Registered on `celery@Louises-MBP`: `connectivity_probe`, `judge_transcript`, `summarize_conversation`, `embed_chunks` (plus `distill_export`). `farm_status.json` `status=ok` `workers_responding=true`.

## vs HANDOFF_STATUS.md §3/§4

| Item | Documented seed | Live |
| --- | --- | --- |
| WSL Docker CE boot task | 03au 20:59 boot; Redis still Desktop | **Match 03au bar** on this 23:35 boot; Redis now on this engine (`03bg`/`bh`) |
| Farm Redis / 6379 owner | Phase C, wslrelay; proof “still due this boot” | **Match Phase C.** Proof already `03bh` PASS; post-logon reconfirm same StartedAt / wslrelay |
| Desktop AutoStart / HKCU Run | off | **Match** (false / absent). Phase C was not “silently” re-triggered; it stayed cut over |
| WireGuard hub | Up, 10.90.90.1/28 | **Match** |
| farm-status logon | unverified | **Changed:** real delayed logon 00:18:03 |
| tunnel-relay task missing / no Listen | 03h S4U fail | **Stale seed.** Logon task exists (03s); started at 00:18:03; Listen up. S4U boot gap unchanged |

`scripts/write_handoff_status.py` persistence/orphan seeds updated from this entry, then regenerated.
