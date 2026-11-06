# 2026-09-05dk — Farm dashboard LAN bind: review (no bind change)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dk**.

Research only. Does not change `FARM_DASHBOARD_HOST`, firewall, or
`server.py`. Follows the 2026-09-05dh EOD note that pid 28216 was
listening on **`192.168.50.208:8765`** while hub Redis stayed
`127.0.0.1` + overlay `10.90.90.1`.

## Is the LAN bind intentional?

**Yes — it is coded as the default, and loopback/overlay are
forbidden.** Not an accident.

`worker_farm/dashboard/server.py` header: bind “a private LAN IPv4
only (**never** `0.0.0.0` / loopback / `10.90.90.x`)”.
`collect.is_forbidden_bind_host` rejects `0.0.0.0`, `127.0.0.1`,
`localhost`, `::1`, unspecified, link-local, **and the entire
`10.90.90.0/24` WireGuard hub range**. `resolve_bind_host` prefers
`192.168.50.*` (comment: home Ethernet). `Start-FarmDashboard.ps1`
says the same. On start it tries to **create a Private-profile inbound
TCP allow** for :8765 (`FarmDashboard TCP 8765 Private`).

That is the opposite of Redis: `worker_farm/README.md` — Redis is
`127.0.0.1`; Mac reaches it via **tunnel-relay on `10.90.90.1:6379`**,
not the home LAN.

The dashboard does **not** need LAN for the Mac worker. Celery/Redis
already use the overlay. LAN :8765 is for **a browser on another
192.168.50.x host** (phone, laptop), not for farm jobs.

## What :8765 actually exposes

Stdlib `ThreadingHTTPServer`. **GET only** (`do_GET`; no `do_POST`).
**No auth**, no TLS, no token.

| Path | Effect |
|---|---|
| `/` `index.html` | Status page (polls the API) |
| `/api/healthz` | `{"ok": true}` |
| `/api/dashboard` | Full JSON (below) |
| else | 404 |

It does **not** submit Celery jobs, talk to Redis, or enqueue Qwythos.
It **reads** `farm_status.json`, tails daemon/relay logs, runs
`farm_health --json` in the farm venv, and checks Windows services /
`10.90.90.1:6379` listen / docker ps.

`/api/dashboard` includes: overall health, snapshot
(`broker_reachable`, worker names e.g. `celery@Louises-MBP`, latency,
redacted `snapshot_error`), WireGuard hub service state, spoke
inference, tunnel-relay process + last log line, Redis docker
name/status, registered **task names** (not job bodies), last 20
outage/recovered log lines. Redis URLs go through
`redact_secrets` (`redis://:***@`).

**Not in the payload:** prompts, chat text, summarize envelopes, AES
keys, Redis password, Celery args.

So: **unauthenticated read of farm topology and health**, not a
control plane and not a prompt dump.

## Home LAN vs the rest of the stack

| Listener | Bind | Auth | Can run jobs / see prompts? |
|---|---|---|---|
| Hub Redis | `127.0.0.1` + overlay `10.90.90.1:6379` | password | Yes (broker) |
| Desktop GUI | loopback `:8760` | none, local | Yes (chat) |
| Farm dashboard | **LAN `192.168.50.208:8765`** | **none** | **No jobs / no prompts** |
| Edge gateway | overlay `10.90.91.1` + loopback | token | Phone path |

Real exposure on a **trusted Private home LAN**: any client that can
reach 192.168.50.208:8765 learns that a worker farm exists, the Mac
worker hostname, hub/relay/Redis-up, and which Celery task names are
registered. Guest/IoT on the same Private profile is enough. It is
**not** job injection and **not** Redis. It **is** looser than the
broker’s bind discipline, and the code **refuses** the tighter
interfaces.

Private firewall (not Public) is a mitigator, not auth.

## Recommendation

**Do not treat the current LAN default as “aligned and fine.”** It was
a deliberate “open on the house Ethernet” choice, but the operator
surface is the **workstation** (and optionally the overlay). The Mac
does not need :8765.

**Preferred later default (not this ticket):** bind **loopback**,
optionally also **`10.90.90.1`**, same family as Redis/relay. Keep
`FARM_DASHBOARD_HOST=192.168.50.208` as an **explicit opt-in** if a
phone on Wi-Fi must hit the page without a tunnel.

**Do not leave LAN as the forced default** (today you cannot even pass
`127.0.0.1` without `ValueError`). That inverts the farm’s bind
policy.

Until a bind PR: acceptable **risk** on a small trusted LAN for a
read-only health page; **not** acceptable as an unspoken equivalent
of Redis hardening. dh was right to flag it.

No process killed, no bind changed, no firewall rule edited.
