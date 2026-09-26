# Design: private-overlay PowerInfer-2 edge gateway (Phase D)

| Field | Value |
|---|---|
| **Document** | Workstation-side edge gateway for the Termux contract |
| **Date** | 2026-09-05 |
| **Status** | v1 built 2026-09-05 (server-only). G1–G10 accepted. Termux `--gateway` still off (G10). |
| **TODO** | `TODO.md` “Implement and review a private-overlay edge gateway…” |
| **Plan** | `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md` Phase D + Deferred work |
| **Contract** | `local_agent/worker_farm/termux_powerinfer2_edge_worker.py` (inert) |
| **Out of scope here** | Pixel contact, Termux compile, NDK rebuild, farm Redis/ACL edits, Equal Shares, ComfyUI, GPU, model download, enabling `--once` on a phone |

This is the implementable spec for the missing gateway. The phone worker is
already written and tested as a **client contract**. Its endpoints do not
exist. Phase D forbids a Pixel worker run until this gateway is implemented
**and independently tested**.

**G1–G10 were accepted 2026-09-05.** v1 is the workstation SQLite gateway
in `local_agent/edge_gateway/`. It does not start the Termux worker and
does not edit the farm WireGuard hub.

---

## Overview

The architecture in the plan is:

```text
Pixel / Termux
  sparse runtime + small, approved model
          |
          |  mTLS or private-overlay HTTPS, per-phone token
          v
Workstation edge gateway (future, loopback/private overlay only)
  validates capability, size, lease, and result
          |
          |  local-only authenticated Redis/Celery
          v
Existing worker farm
```

Two different hops are in that picture. Mixing them is how a lost phone
becomes a farm incident.

| Hop | Who talks | Credential | MVP? |
|---|---|---|---|
| Phone → gateway | Termux worker | per-device token (+ mTLS if signed off) over a **phone** private overlay | **Yes** — this is Phase D |
| Gateway → farm Redis/Celery | workstation process | existing farm broker password / AES key / Redis ACL | **No for MVP** — see sign-off G3 |

The phone must never receive the farm Redis password, AES key, Celery URL, or
a route to `10.90.90.1:6379`. A lost phone with those would claim, inspect, or
poison workstation work (plan, Architecture boundary).

The live farm overlay is already `10.90.90.0/28` (hub `10.90.90.1`, Mac
`10.90.90.2`, Redis relay on the hub). The Pixel is **explicitly out of
scope** for that mesh (`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md`).
Do not add the phone as another `/32` peer on `10.90.90.0/28`.

---

## Where the gateway runs

**Workstation only** (DuranGamingPC). Same machine as the farm hub, **not**
inside the Mac Celery worker, not in Termux, not in `local_agent/server.py`,
not on LAN WiFi, not on `0.0.0.0`.

| Surface | Bind | Who may connect |
|---|---|---|
| Phone API (`/v1/edge/…`) | dedicated overlay unicast, never loopback (the contract **rejects** `127.0.0.1` / `localhost` / `::1`), never `0.0.0.0`, never the home LAN NIC | one Pixel, via the phone overlay |
| Operator admin (inject/revoke) | `127.0.0.1` only, separate port | operator on the workstation |
| Farm Redis | not bound, not opened, not imported in MVP | nobody from this process |

Recommended phone overlay (sign-off G1): a **new** WireGuard `/30`, e.g.
`10.90.91.0/30`.

- Workstation: `10.90.91.1`, AllowedIPs = `10.90.91.2/32` only
- Pixel: `10.90.91.2`, AllowedIPs = `10.90.91.1/32` only
- No route to `10.90.90.0/28`, no route to LAN RFC1918, no NAT into Redis
- Gateway listen: `https://10.90.91.1:<port>` (or a name that resolves only
  on that overlay). That satisfies the worker's “private-overlay workstation
  address, not loopback” check.

The existing farm tunnel (`WireGuardTunnel$hub` / `10.90.90.1`) stays
untouched. Phone private keys and the farm hub private key are different
objects; losing the phone key must not imply losing the farm hub key.

TLS: terminate on the gateway with a workstation server cert. **G2 accepted:
mTLS is on for the first listen** (client cert required; token theft without
the cert is not enough).

**G4 accepted:** phone HTTPS `https://10.90.91.1:8743`, admin HTTP
`http://127.0.0.1:8744`. Not 6379, 8188, 11434, 11435, or 8765.

---

## Existing contract the gateway must speak

Do not invent a second API. The inert worker already defines:

| Item | Value in `termux_powerinfer2_edge_worker.py` |
|---|---|
| Claim | `POST /v1/edge/jobs/claim` body `{"capabilities":["edge_text_inference"]}` |
| Complete | `POST /v1/edge/jobs/{id}/complete` body `{id, status, result}` |
| Auth header | `Authorization: Bearer <token>` |
| Client header | `X-Edge-Worker: termux-powerinfer-contract-v1` |
| Scheme | HTTPS, no userinfo/query/fragment |
| Token file | `$HOME/.config/local-agent/edge-token`, mode 600, length ≥ 24 |
| Allowlist | `kind == "edge_text_inference"` only |
| Prompt cap | 12 000 characters |
| Token cap | 512 (`max_tokens` default 256, range 1–512) |
| Result cap | last 16 000 chars of stdout |
| Threads | 1–4, default 2 |
| First mode | `--once` (at most one claim). Poll ≥ 15 s only after Phase D passes |

Job payload the gateway may emit:

```json
{"id": "<≤120 chars>", "kind": "edge_text_inference", "prompt": "<non-empty ≤12000>", "max_tokens": 256}
```

Complete statuses the worker already produces: `completed`, `timed_out`,
`runtime_failed`, `refused`. The gateway treats unknown statuses as `refused`.

The worker also validates kind/size **on the phone**. The gateway must
enforce the same limits **again**. A compromised or edited Termux script is
the threat; client-side checks are not a control.

Tests that already lock the client side:
`local_agent/worker_farm/test_termux_powerinfer2_edge_worker.py`
(HTTPS/non-loopback, allowlist, shell-free argv). Gateway tests, when
built, are a new module. Do not weaken those client tests.

---

## Minimal viable version (Phase D)

Goal: one operator-injected, non-sensitive `edge_text_inference` job;
one Pixel `--once` claim; one bounded result stored on the workstation;
farm credentials never leave the farm tree.

### Process

A dedicated stdlib-or-thin HTTPS server, own venv, own config file, own
SQLite ledger. It must **not** load `local_agent/worker_farm/.env`,
`.env.mac_worker.generated`, or `runtime/redis-acl/`. Pattern to copy
(metadata only): `job_registry.py` claim-once / idempotency-key uniqueness.
Do not reuse the farm ledger database file.

Disabled unless an explicit `--listen` flag and a config that names the
overlay bind address. Default is off, matching the worker.

### Data (SQLite, workstation disk, not Redis)

| Table | Holds |
|---|---|
| `devices` | `device_id`, token hash (not raw token), optional client-cert fingerprint, capabilities, revoked_at, rate counters |
| `jobs` | `job_id`, kind, prompt (operator-supplied), max_tokens, state, lease_device, lease_until, idempotency_key, result_truncated, result_chars, status |
| `replays` | completed `(device_id, job_id)` and request nonces |

States: `queued` → `leased` → `completed` | `refused` | `expired`.
No `distill` / `summarize` / `embed` / `judge` / render kinds exist in this
database.

### Claim

1. TLS (+ mTLS if G2). Reject if bind peer is not the overlay.
2. Look up Bearer token by hash. Missing / revoked / wrong length → 401,
   no job body.
3. **Ignore** the client's `capabilities` list as authorization. The
   device row is the allowlist. If the device is not granted
   `edge_text_inference`, 403.
4. One in-flight lease per device. If a non-expired lease exists, return
   that same job (idempotent claim) or 409 — pick one in implementation
   and test it; do not mint a second job.
5. Atomically move one `queued` job to `leased` with `lease_until = now +
   timeout` (default 300 s, max 900 s, matching the worker).
6. If none queued, `{ "job": null }` (worker treats this as idle).
7. Response job must already satisfy kind / 12 000 / 512. Never send a
   farm envelope, artifact URI, Redis URL, or AES material.

### Complete

1. Same device auth as claim.
2. `id` must match the device's current lease (or a just-expired lease
   still in `leased`, once). Foreign id → 403, no state change.
3. Result truncated to 16 000 chars **on the gateway** even if the phone
   already truncated.
4. Idempotent: a second complete with the same `{id, status, result}`
   returns the stored row. A second complete with a **different** body
   is replay abuse → 409, first result wins.
5. After success, lease is consumed. Further claims may take a new job
   only if the operator queued one. Phase D queues exactly one.

### Revocation

Operator admin (`127.0.0.1` only):

- `revoke_device(device_id)` sets `revoked_at`; subsequent claim/complete
  are 401. In-flight lease is cancelled, job returns to `queued` **or**
  is marked `expired` (sign-off G8: prefer `expired` so a compromised
  phone cannot be raced to reclaim).
- Token rotation issues a new token hash; the old hash dies immediately.
- If mTLS is on, revoked cert fingerprint is refused at handshake.

Revoking a phone must not rotate farm Redis ACL, Mac worker creds, or the
farm WG hub key.

### Result-size and logging

- Store at most 16 000 chars of `result`.
- Logs: timestamp, device_id, job_id, status, prompt_chars, result_chars,
  peer overlay IP. **Not** prompt text, **not** result text, **not** the
  bearer token, **not** farm secrets.
- Phase D acceptance: “no raw artifact content in logs.”

### Independent test (before any phone)

Loopback admin injects one job. A workstation test client uses a
**hosts-file or overlay-namespace** name that is not `127.0.0.1` in the
URL string (the worker forbids loopback) **or** a thin contract fuzzer
that speaks the same HTTP without going through Termux. Prove:

- happy path claim → complete
- revoked token
- oversized prompt rejected at inject
- second claim during lease does not yield a second job
- complete replay with mutated result is 409
- process environment does not contain `REDIS_PASSWORD` / `FARM_BROKER_URL`
  / AES key names
- listen socket is not `0.0.0.0`

Only then is a Pixel `--once` allowed (still a later, signed-off step).

### Explicitly not in MVP

- Bridging results into Celery/Redis
- Polling (`--poll-seconds`)
- More than one device
- Historical chat, artifacts, decrypt, render, file-edit, model download
- 21B model, NPU/NNAPI claims
- Joining `10.90.90.0/28`
- Changing `termux_powerinfer2_edge_worker.py` allowlist

---

## Threat model (lost / compromised Pixel, gateway in place)

Assume the attacker has the phone: Termux home, `edge-token`, llama-cli,
the 3B/21B weights if they were copied, and the phone WG private key.

### Still possible

| # | Action | Why it remains | Mitigation that is in MVP |
|---|---|---|---|
| T1 | Run the on-device model offline | Weights and binary are on UFS | Do not copy sensitive models; Step 2 uses the 3B smoke model only |
| T2 | Claim the one queued `edge_text_inference` job and read its prompt | That is the feature | Queue only non-sensitive prompts; never chat exports |
| T3 | Return a fake `completed` result | Phone is the runtime | Treat results as untrusted text; no auto-promotion to memory/farm |
| T4 | DoS claim/complete | They have a valid token until revoke | Rate limit + one lease + revoke |
| T5 | Edit the Termux script to skip client caps | Client checks are advisory | Gateway re-enforces kind/size; extra fields ignored |
| T6 | Extract the overlay key and token | Device theft | Revoke device; overlay key ≠ farm hub key |

### Must remain impossible

| # | Action | Control |
|---|---|---|
| B1 | Read farm Redis password or AES key | Never copied to phone; gateway process does not load farm `.env` |
| B2 | Connect to Celery / `10.90.90.1:6379` | Phone overlay has no route there; gateway is not a Redis proxy |
| B3 | Claim `summarize` / `embed` / `distill` / `judge` | Those kinds do not exist on the edge ledger |
| B4 | Enlarge the allowlist by sending `capabilities: ["*"]` | Server uses device row, not the JSON list |
| B5 | Replay last week's complete to overwrite today's | First complete wins; job id consumed |
| B6 | Mint a second job while one is leased | One in-flight lease per device |
| B7 | Receive historical chats, artifact bytes, decrypt | Not a job field; not an endpoint |
| B8 | Trigger ComfyUI / file edit / GPU | No such route; gateway is not `server.py` |
| B9 | Use a revoked token after operator revoke | Token hash + optional cert fingerprint |

### Residual risk the operator accepts by turning this on

A stolen phone can still (a) burn local electricity/thermals on the copied
model, (b) observe whatever single prompt was queued at theft time, (c)
submit a lying result for that job. That is strictly smaller than “farm
credential theft,” which is the failure mode the plan exists to prevent.

If G1 is rejected and the phone is added to `10.90.90.0/28`, **B2 becomes
a network-reachability problem**, not just a credential problem. Redis ACL
would then be the only remaining barrier. That is not acceptable for MVP.

---

## Phase D acceptance mapped to this design

| Plan requirement | How MVP meets it |
|---|---|
| Private overlay + gateway implemented and independently tested | Overlay `/30` + workstation tests before Pixel |
| One `--once` benign job | Operator injects exactly one row |
| One claimed task, one bounded result | Lease + 16 000-char store |
| No Redis credential on the phone | Token/cert only; farm `.env` never packaged |
| No raw artifact in logs | Size/id only |
| No model process after completion | Worker already does not daemonize; phone-side check in Step 2 |
| Thermal/battery observed | Step 2 / Phase A, not this gateway |
| Polling only after, interval ≥ 15 s | Not enabled in MVP |

---

## Relation to TODO Step 2 (Pixel test)

This gateway **blocks the worker path** (claim/complete, “phone batches”).
It does **not** block a strictly local Phase A/C thermal smoke:
`llama-cli -m … --no-cnv -t 2 -n 32 -p "health check"` on the Pixel with
no `--gateway`. That local smoke still must not root the phone, must not
claim NPU, and must not copy farm secrets.

If Step 2 is interpreted as Phase D worker acceptance, it waits on this
build **and** on the sign-off list below. Do not “temporarily” point the
Termux worker at the farm Redis URL to unblock it.

---

## Operator sign-off (required before build)

| ID | Decision | Recommended default | Why it needs a human |
|---|---|---|---|
| **G1** | Phone overlay vs farm mesh | New `10.90.91.0/30`, **not** a peer on `10.90.90.0/28` | Farm Redis is reachable on the existing hub. Phone membership is a farm exposure. Address must not collide with LAN. |
| **G2** | mTLS on day one vs overlay + bearer token first | **Accepted: mTLS on for the first listen.** Client cert + bearer. | Token theft without the device cert is not enough. |
| **G3** | May the gateway process import farm `.env` / talk to Redis in v1? | **No.** Local SQLite only. Farm hop is a later design. | This is the credential boundary. A “thin proxy” is how Redis leaks into the phone path. |
| **G4** | Phone-facing hostname/port | **Accepted: phone `https://10.90.91.1:8743`, admin `http://127.0.0.1:8744`.** | Not 6379/8188/11434/11435/8765. |
| **G5** | Device identity ceremony | Operator generates token (and optional cert) on the workstation; copies token file over USB/ADB; never through chat/farm | Matches Phase B “USB/ADB or operator-approved immutable download.” |
| **G6** | Benign Phase D prompt text | A fixed, non-sensitive health string, ≤ 12 000 chars, no chat export | Whatever is queued is readable by a stolen phone (T2). |
| **G7** | Result handling | Store on workstation; **no** auto-route into agent memory, Chroma, or Celery | T3: results are attacker-controlled text. |
| **G8** | Revoke-during-lease | Mark job `expired`, do not re-queue to the same device | Prevents a race after theft. |
| **G9** | Log retention | Job id + sizes only; bounded file; no prompt/result | Plan: no raw artifacts in logs. |
| **G10** | Enable Pixel `--once` | Only after independent workstation tests pass and G1–G9 are accepted | Phase D sentence 1: overlay and gateway first. |

G1–G10 accepted 2026-09-05. v1 package: `local_agent/edge_gateway/`.
`--listen` is still off by default and refuses to bind if `10.90.91.1` is
not present (no `0.0.0.0` fallback). Overlay conf is generated by
`Generate-EdgePhoneOverlay.ps1` without `-Install` and does not edit
`worker_farm/wireguard/hub.conf`. Token delivery remains USB/ADB (G5).
The Termux script stays inert (G10).

---

## Non-goals

- Replacing WireGuard with a public HTTPS listener “just for the test”
- Putting the gateway inside `local_agent/server.py` (that process has GPU
  and file-edit gates; the phone must not share it)
- Teaching the phone Celery
- Rooting for memory-efficient mode
- Claiming Tensor/NPU offload
- Expanding `ALLOWED_JOB_KINDS`
