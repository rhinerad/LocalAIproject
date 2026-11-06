# 2026-09-01 — Multi-node worker-farm plan and connectivity-probe task

## Scope

Operator wants to start using several already-owned idle LAN computers (4+,
mixed Windows/Linux/Mac, plus a Pixel phone) for background work now, ahead
of the dedicated 10-node cluster hardware. Generalized the existing
single-laptop `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md`
to N machines and implemented only the "prove connectivity first" milestone
the operator chose, per `docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md`.

The Pixel phone is explicitly excluded from this track — it has its own
already-designed, credential-free Termux edge-worker contract and mixing it
into Celery/Redis would cross a boundary that contract was built to keep
closed. Not addressed here; flagged in the new plan doc as a separate,
later decision.

## Code changes

- `local_agent/worker_farm/celery_app.py`: `_is_authenticated_loopback_redis_url`
  now also accepts a single fixed WireGuard tunnel-hub address
  (`FARM_TUNNEL_HUB_HOST = "10.90.90.1"`), not `127.0.0.1` only. This is the
  exact widening the Phase 1.5 plan doc pre-flagged as necessary once a
  secondary node was actually implemented, and only that one address — an
  arbitrary private IP (e.g. `192.168.50.10`) is still rejected, covered by
  a new test. Does not itself open any network path: Docker's
  `127.0.0.1:6379:6379` publish rule is untouched, so nothing reaches Redis
  without the (not-yet-built) WireGuard tunnel and relay also running, and
  nothing reads another node's keys without its own correctly scoped ACL.
- `local_agent/worker_farm/tasks.py`: added `connectivity_probe`, a new
  Celery task returning only `hostname`, `platform`, `worker_pid`,
  `received_at`. No file, encryption, job-registry, or historical-export
  access. Routed to its own `probe` queue (never `distill`) in
  `celery_app.py`'s `task_routes`.
- No changes to `Add-Phase1SecondaryWorkerCredential.ps1` or
  `relay/tunnel_relay.py` were needed — both were already written generically
  enough to support more than one secondary node (verified by reading them
  before touching anything).

## Tests

Added to `local_agent/worker_farm/test_farm_core.py`:
- `test_phase1_broker_url_accepts_the_one_tunnel_hub_address` — confirms the
  widened check accepts only the exact hub address/port/db combination and
  still rejects a wrong port, wrong db, wrong scheme, missing password, a
  peer address instead of the hub, and an arbitrary private IP.
- `test_worker_app_registers_the_connectivity_probe_task` — subprocess
  registration test mirroring the existing `distill_export` one, proving
  `worker.py`'s actual Celery load path registers the new task (not just
  that the source file defines it).
- `test_connectivity_probe_returns_only_harmless_identity_fields` — direct
  call confirming the task body never returns more than the four documented
  fields.

Ran `python -m unittest local_agent.worker_farm.test_farm_core -v` from the
repository root (Celery/cryptography installed into this session's Python):
**16 passed, 1 skipped** (the direct-call test skips when this test process's
own `tasks` module has no configured app — the module-level import-time
behavior already relied on elsewhere in this file; the subprocess test above
is the one that actually proves registration with a real broker URL set).

## What was not done

No WireGuard tunnel was created, no ACL credential was applied to the live
Redis container, no relay was started, and no worker was run on any other
machine — all of that requires hands-on access to physical machines and
terminals this agent doesn't have. The new plan doc gives the exact
per-machine command sequence for the operator (or a session with that
access) to run next.
