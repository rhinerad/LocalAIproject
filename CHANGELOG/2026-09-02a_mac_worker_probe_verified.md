# 2026-09-02a — Mac worker connectivity probe verified end-to-end

## What happened

Continuation of the multi-node worker-farm setup started in
`CHANGELOG/2026-09-01i_wireguard_hub_standup.md`.

## Root cause identified and fixed

Mac worker (`celery@Louises-MacBook-Pro.local`, PID 29584/29587) was connected
and showing "ready" but never returned task results.

**Cause:** `relay/tunnel_relay.py` had `MAX_CONCURRENT_CONNECTIONS = 8`.
Celery's Kombu transport opens ~8 persistent broker connections (heartbeat,
consumer/BRPOP, events, control, unacked monitor). When the task completed and
`store_result` opened a 9th connection to write the result, it queued behind
the semaphore. The Mac's redis-py `socket_timeout` expired before the relay
acquired a slot, raising `redis.exceptions.TimeoutError: Timeout reading from
socket`. The task failure result was then stored — but only after the previous
BRPOP connection was killed and the retry connection opened.

**Secondary issue:** The existing relay (PID 37428) and a second relay instance
(PID 40504) were both running. Only one successfully binds the port; the second
exits silently. After killing both and restarting, the new relay correctly
logged `max 64 concurrent`.

## Fix

- `relay/tunnel_relay.py`: `MAX_CONCURRENT_CONNECTIONS` 8 → 64
- Killed both stale relay processes (PIDs 37428, 40504)
- Restarted relay: `python tunnel_relay.py --bind-ip 10.90.90.1`

## Probe result (verified)

```
{
  "hostname": "Louises-MacBook-Pro.local",
  "platform": "macOS-13.7.8-x86_64-i386-64bit",
  "worker_pid": 29587,
  "received_at": 1788328248.21
}
```

Task ID `720fc45b-a92e-4a18-a2f9-962b5c827bca` returned SUCCESS in < 1 second.

## Files modified

- `local_agent/worker_farm/relay/tunnel_relay.py` — connection limit 8 → 64

## What remains

- ACL DENY probe: verify `mac_worker` cannot read a `distill`-queue or
  `source_*` key (from the original plan in the standup CHANGELOG)
- Repeat peer/credential steps for each additional machine (.3, .4, ...)
- The relay should be added to a launcher/autostart so it survives reboots
