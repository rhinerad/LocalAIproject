# 2026-09-03ba — WSL Redis migration Phase A PASS: Windows 127.0.0.1:16379 reaches Ubuntu Docker CE

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

**Result: PASS.** A throwaway `redis:7-alpine` on Ubuntu-24.04 Docker CE published `127.0.0.1:16379:6379` (same bind shape as farm compose). Windows `127.0.0.1:16379` accepted TCP and returned Redis `+PONG`. The NAT-vs-mirrored localhost gate in `2026-09-03az` is proven for this host/WSL version. Fallbacks (mirrored WSL, boot-time loopback proxy, relaxing local-only bind) are **not** needed for that hop.

Did **not** touch `local-agent-phase1-redis`, `worker_farm_redis-data`, Docker Desktop AutoStart/HKCU Run, compose.yaml, or `.env`. Farm container stayed `4a2fc7893796` `127.0.0.1:6379` healthy throughout.

Id from `python scripts/next_changelog_id.py --date 2026-09-03` immediately before write: **2026-09-03ba**. Plan: `2026-09-03az`.

## What ran

1. Confirmed Ubuntu CE `docker info` ok; no guest/Windows listener on 16379; farm Redis Up 40+ min healthy.
2. `wsl -d Ubuntu-24.04 -- docker pull redis:7-alpine` (digest `sha256:ff02b58f971e…`, image `ff02b58f971e`, left cached for a later cutover; not a running farm container).
3. `docker run -d --name wsl-phaseA-16379 --restart=no -p 127.0.0.1:16379:6379 redis:7-alpine`
4. Guest: `ss` `LISTEN 127.0.0.1:16379`; `docker exec redis-cli ping` = `PONG`.
5. Windows (21:49:29): `Test-NetConnection 127.0.0.1:16379` **TcpTestSucceeded=True**; `TcpClient` connected; Python `PING` → `b'+PONG\r\n'`. `Get-NetTCPConnection` Listen `127.0.0.1:16379` OwningProcess **wslrelay** (pid 12080), not `com.docker.backend`.
6. WSL NAT `172.29.159.194:16379` from Windows **timed out** (expected: publish was loopback-in-guest only). Inside WSL, `127.0.0.1:16379` PONG also succeeded.
7. `docker rm -f wsl-phaseA-16379`. After cleanup, Windows `127.0.0.1:16379` timed out. Ubuntu `docker ps` only `wsl-boot-probe`. Farm Redis still `4a2fc7893796` Up healthy on 6379.

`.wslconfig` remains NAT (`memory=24700MB`, no `networkingMode=mirrored`). Localhost relay via `wslrelay` is enough for a guest `127.0.0.1` Docker publish on this machine.

## What this does not prove

- Farm Redis on Ubuntu CE, volume copy, ACL restore from `runtime/redis-acl`, or `START_PHASE1_BROKER.ps1` using `wsl docker`.
- Port **6379** specifically (Desktop still owns Windows 6379). 16379 was the spare-port gate only.
- Boot-time publish (this probe was from an already-logged-in session). Delayed-login proof remains Phase C of `2026-09-03az`.
- Mac / `10.90.90.1:6379` (tunnel-relay is still logon).
- That opening Docker Desktop later cannot steal 6379.

## Next (still not executed)

Phase B of `2026-09-03az`: point `START_PHASE1_BROKER.ps1` / `doctor.py` / Restore at Ubuntu `docker` behind a switch, default Desktop until cutover. Then Phase C maintenance window. Do not disable Desktop AutoStart yet.
