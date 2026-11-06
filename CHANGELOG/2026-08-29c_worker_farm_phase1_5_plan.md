# 2026-08-29 — Worker Farm Phase 1.5: secondary-node runbook, scripts, plan

## What changed

Added `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md`, the
runbook/scripts/phased plan for `TODO.md`'s next concrete worker-farm step —
"Add the secondary laptop only after it connects over a private encrypted
overlay with separate broker credentials" — scoped to exactly one additional
trusted node, not the ten-node cluster already planned in
`docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md`.

Added two scripts the plan describes:

- `local_agent/worker_farm/relay/tunnel_relay.py` — stdlib-only asyncio TCP
  relay. Binds only to an explicit, non-loopback IP (refuses `0.0.0.0` and
  any loopback address); forwards raw bytes to the existing loopback Redis.
  Adds no authentication of its own by design — WireGuard and the Redis ACL
  credential are the two real security layers, this is plumbing between them.
- `local_agent/worker_farm/Add-Phase1SecondaryWorkerCredential.ps1` —
  generates a fresh random password the same way `Initialize-Phase1Secrets.ps1`
  does, applies a scoped Redis ACL user (`ACL SETUSER`) restricted to the
  laptop's own queue/key patterns, and writes a `.env.<user>.generated`
  fragment locally. Never prints the password. Refuses to grant the `distill`
  queue to a secondary node.

Widened `local_agent/worker_farm/.gitignore` from the literal `.env` to also
match `.env.*`, since the new script writes `.env.laptop_worker.generated`
and the existing pattern would not have caught it.

Cross-referenced the plan from `TODO.md`, `local_agent/UPGRADE/00_INDEX.md`'s
design-notes list, and both current handoff docs.

## Why

Blocked on the operator's own hands for Phase 1's final live check (Docker
Desktop's engine, from the normal desktop account), which this session cannot
do. `TODO.md`'s explicit next worker-farm step doesn't depend on that check
being finished to be *designed*, so this is the useful parallel work: have
the next phase's runbook and scripts ready rather than idle until Phase 1
clears.

## Verification

- The relay's core forwarding logic was tested directly (bypassing its own
  CLI policy guard) against a dummy echo server in an isolated sandbox: two
  concurrent client connections both received correctly relayed bytes back,
  connection-open/close logging worked, clean shutdown. Separately confirmed
  the policy guard refuses `--bind-ip 0.0.0.0` and `--bind-ip 127.0.0.1` with
  clear error messages and exit code 2.
- The sandbox this session runs in has no non-loopback network interface at
  all (`ip -o -4 addr show` lists only `lo`; a UDP `connect()` to an external
  address raises `Network is unreachable`), so binding to a real tunnel-style
  IP and relaying through it together was not testable here. The two pieces
  (policy guard, forwarding logic) were verified separately instead.
- The PowerShell script could not be run or even syntax-checked here (no
  `pwsh` in this sandbox, and no Docker/Redis/laptop to test against anyway).
  It was written to match `Initialize-Phase1Secrets.ps1`'s existing
  conventions exactly (same `New-RandomBase64` helper, same never-print-the-
  secret discipline, same placeholder/existence refusals) and proofread by a
  second full read-through for PowerShell's variable-then-colon interpolation
  gotcha (`` `: `` escaping in the generated `redis://user:pass@host:port/db`
  URLs and ACL key patterns).
- The Redis ACL rule text in the plan doc and the script is a **draft**,
  explicitly labeled as such in both places: Celery/Kombu's exact Redis key
  usage (`unacked`/`unacked_index` for late-ack retry bookkeeping, `_kombu.
  binding.*`, event pub/sub if ever enabled) needs confirming against a real
  Celery 5.6.3 client before anyone trusts it, the same way the task-
  registration fix earlier this session needed a real Celery app object
  rather than reasoning from documentation alone.

## What is unverified

Everything that requires a second machine, a real WireGuard tunnel, a live
Redis 7 instance, or Docker: the ACL rule's actual effect (including the
`ACL DENY` negative-control probe the plan itself says is required before
trusting it), whether Docker Desktop's WSL2 networking could bind a published
port to a secondary Windows adapter IP directly (the reason the relay exists
instead — untested either way), and the `--aclfile` persistence gap called
out in the script's own header (the ACL user is in-memory only today and is
lost on container restart). None of this was started; see the plan doc's own
"Open questions" section.
