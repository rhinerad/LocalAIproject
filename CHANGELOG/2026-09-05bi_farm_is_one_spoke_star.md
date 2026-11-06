# 2026-09-05bi — Worker farm audit: one-spoke star, not a 4-machine fleet

## Scope

🟣 lane, farm audit follow-up. Investigation only, no hub/peer/config
change.

## Finding

The 2026-09-01 decision to add "4+ already-owned idle LAN machines" never
progressed past the Mac. Confirmed via both `hub.conf`'s single `[Peer]`
block (unchanged since 2026-09-01 23:03) and the live hub's routing table
(only `10.90.90.2/32` exists; `.3`-`.6` return "no route," not a
timeout). Only one Celery worker has ever registered:
`celery@Louises-MBP`. The 2026-09-01 plan itself only ever used
placeholder names (`workshop_pc`, `media_server`, `old_laptop`,
`linux_box`) — a real machine list and OS inventory was left as an open
question and was never subsequently filled in.

This is not a stuck or failed join — there's no record of a second
machine attempting WireGuard and getting stuck. It was deprioritized
once the Mac path worked and the operator's 2026-09-02 directive shifted
focus to engine evaluation; "swarm offload" got marked as largely already
built on the strength of the one working node.

## Recommendation

Don't actively chase the remaining 3+ LAN machines right now — that's
operator-hands-on work (per-box keypair, `Add-WireGuardPeer`, per-machine
Redis ACL, venv, `worker.py`) that was deprioritized, not blocked by
anything technical. Worth doing only if more CPU capacity is actually
wanted beyond what Louise's 2019 16GB Intel Mac provides — that's a
capacity decision, separate from the already-deferred 10-node/60-core
cluster architecture track, which this hub was never meant to be.

## Status

Confirms the farm is healthy at its current one-worker scale. No further
action needed unless the operator wants to actively expand it.
