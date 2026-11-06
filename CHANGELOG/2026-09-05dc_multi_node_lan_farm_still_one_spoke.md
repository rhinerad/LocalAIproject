# 2026-09-05dc — Multi-node LAN farm audit: still one spoke (Mac only)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dc**. Research/audit
only. **No onboarding, no WireGuard peer/hub edits, no farm `.env` /
Redis ACL changes.** Re-checks the 2026-09-01 “4+ idle LAN machines”
decision against live state. Prior related audit:
`CHANGELOG/2026-09-05bi_farm_is_one_spoke_star.md` (same conclusion;
this pass adds live `farm_health` / overlay / credential-file evidence
as of this evening).

## Decision vs what shipped

Operator decision (TODO, 2026-09-01): start using several already-owned
idle LAN machines (4+, mixed Windows/Linux/Mac) **now**, ahead of the
unauthorized 10-node cluster, “prove connectivity first.” Generalized in
`docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md` (hub-and-spoke
WireGuard on `10.90.90.0/28`, one scoped Redis ACL user per machine,
Pixel **out of this Celery track**).

**Done (code + first spoke, 2026-09-01 through 2026-09-05):**

| Piece | Status |
|---|---|
| Hub URL allow-list (`FARM_TUNNEL_HUB_HOST=10.90.90.1`) + `connectivity_probe` | 2026-09-01e |
| WireGuard hub scripts + hub standup (`10.90.90.1:51820`) | 2026-09-01h / 2026-09-01i |
| First peer: Louise’s Mac `10.90.90.2` | 2026-09-01i; ping this session 0% loss |
| `mac_worker` ACL + `.env.mac_worker.generated` | 2026-09-01i; still the **only** generated secondary env |
| `connectivity_probe` E2E (`celery@Louises-MacBook-Pro.local` / later `celery@Louises-MBP`) | 2026-09-02a (relay semaphore 8→64) |
| `judge` / `summarize` / `embed` live on that same Mac | 2026-09-02c/d; README inventory |
| Tunnel-relay logon autostart | 2026-09-03am (TODO’s “relay autostart” line from 2026-09-01 is stale) |
| `qwythos_evaluate` registered on that worker | live this session |

**Not done:** any second LAN machine. Plan placeholders
(`workshop_pc`, `media_server`, `old_laptop`, `linux_box`) were never
replaced with a real inventory. No `.env.<other>.generated`. No
`[Peer]` beyond `10.90.90.2/32`. Next free overlay IP is still
**`10.90.90.3`**.

This is not a stuck join. There is no changelog of a second box
attempting WireGuard. After the Mac path worked, 2026-09-02 focus
moved to engine evaluation; “swarm offload” was marked largely built
on **one** verified node.

## Live node count tonight (2026-09-05 ~18:07 local)

**Celery workers: 1.** Identity: **`celery@Louises-MBP`**.

`farm_health --json` (broker reachable, `status=ok`):

- `workers`: `["celery@Louises-MBP"]` only
- Registered on that worker:
  `connectivity_probe`, `distill_export`, `embed_chunks`,
  `judge_transcript`, **`qwythos_evaluate`**, `summarize_conversation`
- No second hostname in `inspect` / `tasks_by_worker`

Overlay / files (read-only):

- Workstation `hub` iface: `10.90.90.1/28`
- `hub.conf`: **one** `[Peer]`, public key
  `H0IsFuY1eREqu4jWXz94fKR9oC+4qdcBU7d83shvNzo=`, `AllowedIPs=10.90.90.2/32`
- Relay listen `10.90.90.1:6379`: Established remotes **only `10.90.90.2`**
- Ping `10.90.90.2`: 2/2, 19–102 ms
- Secondary env fragments on disk: **`.env.mac_worker.generated` only**
  (`runtime/redis-acl/` same)
- `worker_farm/README.md` “Known worker machines”: **one row**,
  `mac_worker` / 2019 MacBook Pro 16 GB / macOS 13.7.8 x86_64 /
  model `krith/mistral-nemo-instruct-2407-abliterated:IQ4_XS`

Workstation itself is the **hub + Redis + relay**, not a second Celery
spoke in tonight’s ping.

**Not a farm node:** iface `edge-phone` `10.90.91.1/30` is the Pixel
edge-gateway overlay (`docs/design_notes/POWERINFER2_EDGE_GATEWAY_2026-09-05.md`).
The 2026-09-01 plan forbids putting the phone on `10.90.90.0/28` /
Celery. It does not count toward “4+ LAN farm machines.”

## What the plan still lists as remaining (per machine)

From `docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md` § “What to
run… per machine” — **done only for the Mac**:

1. Phase 1 broker up — yes.
2. Keypair on **each** secondary; hub `[Peer]` + node `[Peer]`; ping
   `10.90.90.1` — **Mac only**.
3. `Add-Phase1SecondaryWorkerCredential.ps1 -Queues probe` once per
   machine — **`mac_worker` only**.
4. `tunnel_relay.py --bind-ip 10.90.90.1` — yes (now logon-autostart).
5. Isolated `.venv`, place generated env, `worker.py --queues probe` —
   **Mac only**.
6. Submit `connectivity_probe`; hostname comes back — **Mac only**.
7. ACL DENY per credential + same-session CHANGELOG — Mac: 2026-09-02d
   (honest `~*` distill-envelope read; no admin).

Plan open questions still open: **exact machine list and OS per box**;
whether/when the Pixel joins a *different* track (already designed,
not this overlay); first *real* task after connectivity (Mac later
got judge/summarize/embed/qwythos — that does not onboard more boxes).

TODO still says: repeat `Add-WireGuardPeer` + credential for `.3`,
`.4`, … Hub scripts in `local_agent/worker_farm/wireguard/` already
exist for that; they have not been run for a second peer.

## Concrete next step *if* the operator wants to expand

Do **not** start the 10-node cluster stack. Do **not** grant `distill`.
Pick **one** real idle LAN machine (the plan never named the others).
Assign **`10.90.90.3`**. Hands-on on that box + workstation:

1. Generate a WireGuard keypair **on that machine** (operator-controlled
   channel for the public key; never through this agent / broker).
2. Workstation: `wireguard\Add-WireGuardPeer.ps1` with that public key
   and `10.90.90.3`. Confirm `ping 10.90.90.1` from the new box **before**
   Redis.
3. Workstation: `Add-Phase1SecondaryWorkerCredential.ps1 -Username <id>
   -Queues probe` (new username, not `mac_worker`; do **not** re-run
   the Mac script — it mints a new password and would break Louise’s
   stored credential). Copy the new `.env.<id>.generated` by hand.
4. On the new box: isolated `.venv` from `requirements.txt`, env as
   `.env`, `worker.py --queues probe`.
5. From the workstation: `connectivity_probe` on `probe`; result
   hostname must be **that** machine, and `farm_health` must list a
   **second** `celery@…` identity.
6. ACL DENY probe + CHANGELOG before calling it done. Only then consider
   extra queues (`judge` / `summarize` / `embed`) the way the Mac was
   widened after probe.

Capacity note (2026-09-05bi): expanding is a CPU-capacity choice beyond
the 2019 16 GB Intel Mac, not a prerequisite for the deferred 10-node
architecture, and not blocked by missing hub code.

No farm config was written this pass.
