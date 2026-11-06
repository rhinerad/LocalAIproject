# Worker Farm Phase 1.5 — adding the secondary laptop node (2026-08-29)

## What this is, and what it is not

This is the runbook, scripts, and phased plan for the **single concrete next
step** named in `TODO.md` under "Phase 1 worker-farm bootstrap": *"Add the
secondary laptop only after it connects over a private encrypted overlay with
separate broker credentials."* It is scoped to exactly one additional trusted
node (the operator's laptop) joining the existing Celery/Redis foundation at
`local_agent/worker_farm/`.

It is **not** the ten-node Intel cluster. That larger vision, its RabbitMQ/Ray/
PostgreSQL/MinIO stack, and its four workflows (Judge, Researcher, Teacher/
Student, historical-memory distillation) stay exactly as scoped and gated in
`docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md` — "planning only... No
cluster service, model, download, network listener, or external account is
authorized by this roadmap alone." Nothing here authorizes starting that
cluster either. This document is the small, concrete bridge between "one
loopback-only worker on this machine" and that larger roadmap: it is Phase A's
first real node, sized to two machines instead of ten, so it can actually be
built and tested before the larger plan's capacity/trust gates are attempted.

It is also **not** the parked chat-offload idea in
`docs/design_notes/distributed_compute_assessment.md`. That note is about
moving the *interactive* reasoning LLM's Ollama server to a second box so the
RTX 5080 stays dedicated to ComfyUI — a different subsystem (`router.py`'s
GPU/CPU tiers), a different protocol (Ollama's HTTP API), and a different
trust model (a model-serving endpoint, not a task queue with private data
flowing through it). It remains paused on the question of whether the
candidate second box has a GPU, and nothing here un-pauses it. The two ideas
are related only in that both spend a second physical machine's spare
capacity — if the operator's laptop ever became both a Celery worker *and* a
remote Ollama host, `router.py`'s health-check/fallback design and this
plan's overlay would very likely reuse the same WireGuard tunnel, which is
the one implementation detail worth remembering if that note is ever
un-paused.

No script in this plan has been run. Nothing has been installed on a laptop.
No queue has been exposed beyond `127.0.0.1`. Writing this down is not
authorization to execute it — the live Phase 1 single-node sample (blocked on
Docker Desktop's engine, per `docs/CLAUDE_CODE_CONTINUATION_2026-08-29.md`)
should be accepted first, since this plan builds directly on that same broker
and its `.env`.

## Why a laptop node is safe to add and what changes

Today, Redis is authenticated (`--requirepass`) **and** unreachable from
anywhere but the workstation itself (`127.0.0.1:6379:6379` in
`compose.yaml`). Adding a second real machine means something other than
`localhost` must be able to reach port 6379. That is a genuine, deliberate
expansion of the trust boundary — exactly the one `worker_farm/README.md`
already names as requiring "a private encrypted overlay and separate broker
credentials" before it's allowed. Two independent layers do that work:

| Layer | Mechanism | Stops |
|---|---|---|
| Network | WireGuard point-to-point tunnel, workstation ⟷ laptop only | Anything else on the home LAN from reaching Redis at all, even if it later guesses a password |
| Application | A separate Redis ACL user for the laptop, scoped to its own queues/keys, distinct from the workstation's superuser password | The laptop (or anything using its credential) from reading `distill` jobs, historical-export artifacts, or other users' keys, even though it shares the same Redis instance |

Neither layer is optional. WireGuard without a scoped credential means a
compromised laptop gets the same access as the workstation. A scoped
credential without WireGuard means the password is the only thing standing
between the open LAN and a queue that will eventually carry private data.

## Phase 1.5-A — network: WireGuard tunnel

A point-to-point WireGuard tunnel, not a mesh VPN service (Tailscale/Nebula):
no third-party coordination account, no dependency on an external server
being reachable, keys never leave the two machines. This matches the existing
project bias against external accounts for core infrastructure (see `TODO.md`:
"No... external account is authorized by this roadmap alone").

- Address plan: a bare `/30`, only two usable hosts — `10.90.90.1`
  (workstation) and `10.90.90.2` (laptop). Chosen to be unlikely to collide
  with typical home-router LAN ranges (`192.168.x.x`, `10.0.x.x`); confirm it
  doesn't collide with the operator's actual LAN before use.
- Each machine generates its own keypair locally (`wg genkey | tee privatekey
  | wg pubkey > publickey`, or the WireGuard Windows client's built-in key
  generation). Private keys are never transmitted; only public keys are
  exchanged, once, over a channel the operator controls directly (not through
  this agent, not through the broker).
- The workstation's WireGuard peer listens on a UDP port (default 51820) on
  the LAN interface only — it does not need to be, and should not be, port
  forwarded on the home router. Both machines stay on the same LAN.
- Redis itself is **not** reconfigured to bind to the tunnel interface, and
  `compose.yaml`'s already-verified `127.0.0.1:6379:6379` publish rule is not
  touched. Whether Docker Desktop's WSL2-backed port publishing actually
  binds cleanly to an arbitrary secondary Windows adapter IP (the WireGuard
  interface) is untested here and not worth risking against a foundation that
  currently works. Instead:

### The relay, not a Docker networking change

`local_agent/worker_farm/relay/tunnel_relay.py` is a small stdlib-only TCP
byte relay (no third-party dependency, matching the project's existing
stdlib-only pattern in `termux_powerinfer2_edge_worker.py`). It binds
**only** to an explicit, non-loopback IP passed as a required argument — it
refuses `0.0.0.0` and refuses to guess — and forwards raw bytes to
`127.0.0.1:6379`. It adds no authentication of its own; it is plumbing, not a
security boundary. The two real security layers are WireGuard (below it) and
the Redis ACL credential (above it, inside the relayed connection). Run it on
the workstation, bound to `10.90.90.1`, only while a laptop worker session is
active — it is not part of `START_PHASE1_BROKER.ps1` and does not start
automatically.

## Phase 1.5-B — credentials: a scoped Redis ACL user

`redis:7-alpine` (already pinned in `compose.yaml`) supports full ACL
(`ACL SETUSER`, Redis 6+), not just the legacy single `--requirepass`. The
laptop gets its own username and password, generated the same way
`Initialize-Phase1Secrets.ps1` already generates the main Redis password
(`RandomNumberGenerator`, URL-safe base64, never printed) — never the
workstation's own broker password.

Draft ACL, applied through `redis-cli` inside the existing container (exact
command in the script below):

```
ACL SETUSER laptop_worker on >{generated-password} ~laptop_worker:* ~preprocess ~research ~_kombu.binding.preprocess ~_kombu.binding.research ~celery-task-meta-* ~unacked ~unacked_index resetchannels +@read +@write +@keyspace +@connection -@admin -@dangerous -@scripting -flushall -flushdb -config -shutdown -acl
```

This is a **draft, not a verified rule** — Celery/Kombu's exact Redis key and
command usage (delivery-tag bookkeeping, `unacked`/`unacked_index` for
`task_acks_late`, any event-pubsub channels if worker events are ever
enabled) needs confirming against a real Celery 5.6.3 client before this is
trusted, exactly the same way the task-registration fix in this session
needed a real Celery app object rather than reasoning from documentation
alone. Test it by pointing a throwaway worker at `laptop_worker`'s credential
and confirming both that its own queues work **and** that
`ACL DENY` correctly blocks a `GET` on a `distill`-queue or
`source_*`/`result_*` artifact-ledger key before this is used for anything
beyond the synthetic sample.

`local_agent/worker_farm/Add-Phase1SecondaryWorkerCredential.ps1` (below)
generates the password locally, applies the ACL rule above through the
running Redis container, and writes a laptop-side `.env.laptop_worker`
fragment containing only the `redis://laptop_worker:{password}@10.90.90.1:6379/0`
URL shape — it never prints the password to the console, matching
`Initialize-Phase1Secrets.ps1`'s existing convention, and it refuses to run
unless the main broker is already up (it needs a live Redis to apply the ACL
to).

## Phase 1.5-C — the laptop's own worker process

The laptop runs the exact same `local_agent/worker_farm/worker.py` already in
the repo — cross-platform pool selection (`solo` on Windows/Android, `prefork`
on Linux) is already implemented there and needs no laptop-specific fork. Two
new queues, `preprocess` and `research`, are added to `celery_app.py`'s
`task_routes` only once real task functions exist for them (none do yet —
per `worker_farm/README.md`'s policy table, the laptop is scoped to
"public/approved sources only," so its first real task is more likely a
Researcher-style fetch/extract job than anything touching private exports).
Writing those tasks is out of scope for this plan; it is the natural
follow-up once the tunnel and credential are live-verified.

The laptop's `.env` is **not** a copy of the workstation's. It contains:
- `FARM_BROKER_URL` / `FARM_RESULT_BACKEND` using the `laptop_worker`
  credential and the workstation's tunnel address (`10.90.90.1`), not
  `127.0.0.1` — `celery_app.py`'s existing
  `_is_authenticated_loopback_redis_url` check deliberately requires
  `127.0.0.1`, so it will (correctly) refuse this URL. That function needs a
  second, explicit allow-list entry for the tunnel address once this phase is
  actually implemented — not changed here, since loosening that check without
  the tunnel actually existing yet would just widen what the workstation's
  own worker/submitter accept. Flagging it now so it isn't missed later.
- `FARM_QUEUES=preprocess,research` (never `distill` — the laptop must not be
  able to claim historical-export jobs even if it could authenticate, and the
  ACL above already makes that a second, independent enforcement point).
- Its own `FARM_ENCRYPTION_KEY_B64`, if it ever produces artifacts that need
  encryption, is a separate concern from the broker credential and is not
  designed here — no task exists yet that would need it.

## What to run, once the operator decides to proceed

1. Confirm the existing single-node Phase 1 sample has been accepted (see
   `docs/CLAUDE_CODE_CONTINUATION_2026-08-29.md`'s numbered sequence). This
   plan assumes a working broker, not a blocked one.
2. Generate and exchange WireGuard keys on both machines; confirm
   `10.90.90.1` ⟷ `10.90.90.2` ping over the tunnel before touching Redis.
3. On the workstation: `local_agent\worker_farm\Add-Phase1SecondaryWorkerCredential.ps1`
   — applies the ACL, writes the laptop's env fragment to a file the operator
   copies across themselves (never transmitted by this agent).
4. On the workstation: run `tunnel_relay.py` bound to `10.90.90.1`, only for
   the duration of the test.
5. On the laptop: install the same `requirements.txt` into its own isolated
   `.venv`, place the generated `.env.laptop_worker` as its `.env`, and run
   `worker.py --queues preprocess,research`.
6. Verify with `ACL DENY` probes (step B above) before considering this done,
   and add the result to a same-session `CHANGELOG/` entry — this plan does
   not count as verification of itself, per this project's standing rule.

## Open questions this plan cannot resolve alone

- **Laptop OS is unknown here.** `worker.py`'s pool selection already handles
  Windows/Linux/Android; WireGuard has native clients for all three, so
  nothing above assumes one. Confirm before running step 3.
- **Whether Docker Desktop's WSL2 networking would have worked for a direct
  bind to the tunnel interface instead of the relay** is untested. The relay
  was chosen specifically to avoid depending on the answer, but if a future
  session confirms direct binding works, the relay becomes unnecessary
  overhead and can be dropped.
- **Whether `10.90.90.0/30` collides with anything already on the operator's
  network** needs a one-time manual check on the operator's side; it isn't
  something this agent can see.

These are recorded here rather than left as silent assumptions, in keeping
with `distributed_compute_assessment.md`'s own pattern of ending on its one
open question instead of guessing past it.
