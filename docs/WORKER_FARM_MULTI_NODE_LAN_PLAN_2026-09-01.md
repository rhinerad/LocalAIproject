# Worker Farm — multiple idle LAN machines, before the 10-node cluster (2026-09-01)

## What this is, and what it is not

The operator has 4+ idle computers on the home LAN today (mixed Windows/
Linux/Mac) and a Pixel phone, and wants them contributing spare capacity now,
ahead of the dedicated 10-node/60-core/160-GB cluster hardware named in
`docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md` (that plan remains
"planning only" and unauthorized on its own). This document generalizes
`docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md` — written for
exactly one additional laptop — to an arbitrary number of already-owned LAN
machines, and narrows the first milestone to **proving connectivity only**,
per the operator's own stated priority: get real machines securely joined and
completing real (if trivial) work before writing any new task logic.

It is **not** the RabbitMQ/Ray/PostgreSQL/MinIO ten-node stack or its four
production workflows (Judge, Researcher, Teacher/Student, historical-memory
distillation). Those stay exactly as scoped and gated in the architecture
plan. Nothing here authorizes starting that stack, downloading a model,
processing a real historical export, or granting a worker access to the
`distill` queue.

**The Pixel phone is explicitly out of scope for this document.** It has its
own, already-designed track: the inert, stdlib-only Termux edge-worker
contract (`local_agent/worker_farm/termux_powerinfer2_edge_worker.py`), which
deliberately never receives Redis/AES broker credentials or joins Celery —
see `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md`. Mixing the phone into
this Celery/Redis track would cross a boundary that track was specifically
designed to keep closed. If the phone should contribute here too, that is a
separate, later decision — not a default of "it's idle hardware."

## What's already true, verified while writing this

- The single-node Phase 1 broker + synthetic `--sample` job already completed
  successfully on 2026-08-29 (`local-agent-phase1-redis`, healthy, one
  encrypted `review_required` result) — the prerequisite this plan builds on.
- `Add-Phase1SecondaryWorkerCredential.ps1` was already written generically
  (`-Username`, `-Queues`, `-TunnelIp` parameters) — it needed **no code
  change** to support more than one secondary node. It already refuses to
  grant the `distill` queue to any secondary credential.
- `local_agent/worker_farm/relay/tunnel_relay.py` already accepts up to 8
  concurrent connections through a semaphore — it needed **no code change**
  to relay more than one peer's traffic to Redis.
- `worker.py`'s pool selection (`solo` on Windows/Android, `prefork`
  elsewhere) already covers Windows, Linux, and macOS without change.
- The one real gap: `celery_app.py`'s `_is_authenticated_loopback_redis_url`
  accepted only `127.0.0.1`, which no other machine can ever reach. The
  Phase 1.5 plan doc flagged this exact gap and deliberately deferred fixing
  it until a secondary node was actually being implemented. **Fixed today** —
  see "Code changes made" below.
- No real task exists yet for a secondary node to run. `distill` is
  historical-export-only and forbidden to secondary credentials by the
  credential script itself; `preprocess`/`research` are named in the Phase
  1.5 doc but have no task functions written. A **new, minimal
  `connectivity_probe` task** (added today, see below) fills that gap for
  the "prove connectivity" milestone without inventing scope.

## Topology: hub-and-spoke instead of one point-to-point tunnel

The Phase 1.5 doc used a bare `/30` (workstation + one laptop only). With
4+ machines, the workstation becomes a small WireGuard hub with one peer
section per machine; each secondary machine's own WireGuard config lists
only the workstation as its one peer (a star, not a mesh — machines never
need to reach each other directly for this).

- Address plan: `10.90.90.0/28` (14 usable addresses — room for the current
  4+ machines plus headroom without renumbering). Workstation is
  `10.90.90.1` (unchanged from the Phase 1.5 doc — this is why
  `Add-Phase1SecondaryWorkerCredential.ps1`'s `-TunnelIp` default and the
  relay's `--bind-ip` did not need to change). Each secondary machine takes
  the next free address (`10.90.90.2`, `.3`, `.4`, `.5`, ...).
- Confirm `10.90.90.0/28` doesn't collide with the actual home LAN's router
  range before use — the same manual check the Phase 1.5 doc already named
  as something it cannot verify remotely.
- Each machine still generates its own WireGuard keypair locally; only
  public keys are exchanged once, over a channel the operator controls
  directly (never through this agent, never through the broker) — unchanged
  from the Phase 1.5 doc's rule.
- The workstation's WireGuard interface gains one `[Peer]` block per
  machine (each with that machine's public key and its `/32` allowed-IP);
  each secondary machine's config has exactly one `[Peer]` block, pointing
  back at the workstation's public key and `10.90.90.1`.
- Redis itself is still never reconfigured to bind to the tunnel interface.
  The existing `tunnel_relay.py`, run once on the workstation bound to
  `10.90.90.1`, still forwards every peer's traffic to the already-verified
  `127.0.0.1:6379` — this is exactly why its 8-connection semaphore already
  covers this case without modification.

## Credentials: one scoped ACL user per machine

Run `Add-Phase1SecondaryWorkerCredential.ps1` once per machine, giving each
one its own username and, for this milestone, only the `probe` queue —
**not** `preprocess`/`research` yet, since no task code exists for those and
least-privilege means not granting a queue before there's a reason to:

```
.\Add-Phase1SecondaryWorkerCredential.ps1 -Username workshop_pc   -Queues probe
.\Add-Phase1SecondaryWorkerCredential.ps1 -Username media_server  -Queues probe
.\Add-Phase1SecondaryWorkerCredential.ps1 -Username old_laptop    -Queues probe
.\Add-Phase1SecondaryWorkerCredential.ps1 -Username linux_box     -Queues probe
```

(names are placeholders — use whatever identifies each machine to you). Each
run writes its own `.env.<username>.generated` fragment locally, never
transmitted by this agent; copy each one to its matching machine yourself.
Verify each with an `ACL DENY` probe against a key it should not own (the
same verification step the Phase 1.5 doc already specifies) before trusting
it for anything beyond the connectivity test below.

Note the script's own documented limitation: these ACL users live only in
the running Redis container's memory (no `aclfile` configured) and must be
re-applied if the container restarts — unchanged, not addressed here, to
avoid risking the verified Phase 1 foundation for a feature not yet live.

## Code changes made today

1. **`local_agent/worker_farm/celery_app.py`** — `_is_authenticated_loopback_redis_url`
   now also accepts `redis://<user>:<pass>@10.90.90.1:6379/{0,1}` (a single
   fixed constant, `FARM_TUNNEL_HUB_HOST`), not any private IP. This is the
   exact, narrowly-scoped change the Phase 1.5 doc pre-flagged as necessary
   once a secondary node was actually implemented. It does not open any
   network path by itself — Docker's `127.0.0.1:6379:6379` publish rule is
   unchanged, so nothing reaches Redis without the WireGuard tunnel and relay
   also being live, and nothing reads another user's keys without a
   correctly scoped ACL.
2. **`local_agent/worker_farm/tasks.py`** — added `connectivity_probe`, a
   Celery task that returns only `hostname`, `platform`, `worker_pid`, and
   `received_at`. It touches no file, no encryption, no job-registry state,
   and no historical-export data. Routed to its own `probe` queue in
   `celery_app.py`'s `task_routes` (never `distill`).
3. Tests: `test_farm_core.py` gained a test asserting the widened URL check
   still rejects an arbitrary private IP (`192.168.50.10`) and only accepts
   the one hub address, plus a subprocess registration test mirroring the
   existing `distill_export` one (worker.py's actual Celery load path must
   register the new task, not just the source file defining it), plus a
   direct call confirming the task body only ever returns the four harmless
   fields above. All pass; see `CHANGELOG/2026-09-01e_...md`.

## What to run, once the operator decides to proceed — per machine

1. Confirm the workstation's Phase 1 broker is currently up
   (`SHOW_PHASE1_STATUS.ps1`).
2. Generate a WireGuard keypair on the workstation and on each secondary
   machine; add each machine's public key as a `[Peer]` on the workstation's
   config, and the workstation's public key as the sole peer on each
   machine's config. Confirm each machine can `ping 10.90.90.1` over the
   tunnel before touching Redis.
3. On the workstation, run `Add-Phase1SecondaryWorkerCredential.ps1` once per
   machine (usernames above), each scoped to `-Queues probe`.
4. On the workstation, run `tunnel_relay.py --bind-ip 10.90.90.1`, for the
   duration of the test only — it is not part of `START_PHASE1_BROKER.ps1`
   and does not start automatically.
5. On each secondary machine: install `requirements.txt` into its own
   isolated `.venv`, place its generated `.env.<username>.generated` as its
   `.env`, then run `worker.py --queues probe`.
6. From the workstation, submit a `connectivity_probe` task per machine
   (e.g. `app.send_task("local_agent.worker_farm.tasks.connectivity_probe",
   queue="probe")` from a Python shell with `FARM_BROKER_URL` set) and
   confirm each machine's own hostname comes back in the result.
7. Run the `ACL DENY` verification per credential before considering any of
   this "done," and record the outcome in a same-session `CHANGELOG/` entry
   — per this project's standing rule that a plan does not verify itself.

I cannot perform steps 2, 3 (interactively per machine), 4, or 5 myself — they
require hands-on access to each physical machine and to the terminal running
the broker, which I don't have. What I've done today is the part I could do
safely without touching any of that: the code change the plan itself named as
a prerequisite, the new minimal task, tests for both, and this generalized
runbook so the manual steps above are exact rather than improvised per
machine.

## Open questions this plan cannot resolve alone

- Exact machine list, OS per machine, and which network interface each one
  should use for the tunnel (same as the Phase 1.5 doc's "laptop OS is
  unknown here" note, just for more machines).
- Whether `10.90.90.0/28` collides with the actual home LAN — a one-time
  manual check only the operator can do.
- Whether/when the Pixel phone should join a *different* track (Termux edge
  worker) — not this one, and not decided here.
- What the first *real* task should be once connectivity is proven —
  deliberately left open per the operator's own answer to do this in two
  steps rather than one.
