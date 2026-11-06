# 2026-09-05f — Mac worker outage: frozen/asleep, not a code or registration bug

## Scope

🟡 lane. Diagnosis only, no restart performed, no code changed. Matches the
operator's own account that the Mac was shut down for the night — this
confirms the network-level signature of that, not a surprise failure.

## Finding

Root cause: the Mac worker (`Louises-MBP`) stopped responding around
23:47 EDT on 2026-09-04. Workstation-side farm plumbing (Redis, WireGuard
hub, tunnel relay) is fully healthy — this is not a repeat of the
2026-09-04i registration gap.

Evidence the Mac process/kernel state is hung-or-asleep rather than cleanly
exited: 9 `mac_worker` Redis clients and matching ESTABLISHED TCP sessions
from 10.90.90.2 have not recycled since 2026-09-04 15:38 EDT (the last
`launchctl` kickstart, per `2026-09-04n`); none are in `BRPOP`; the pidbox
control channel is idle ~72 min with a stale cached pong, not a live
response. Hub → Mac overlay traffic is 100% loss; LAN ping to 192.168.50.8
gets short high-TTL replies consistent with a sleep proxy, not an awake
sshd. `inspect.ping()` returns empty; `qwythos_evaluate` registration was
not re-confirmed live (inspect never reaches a worker) but there is no
evidence of a later restart that would have dropped it — the last live
confirmation remains `2026-09-04n`'s registered-tasks check.

## What was not done

No `launchctl` kickstart, no WireGuard bounce, no Redis restart. Nothing
actionable until the Mac is physically awake again — consistent with the
operator's own plan to leave it off overnight.

## Checklist for when the Mac is back (do not skip the order)

1. `launchctl print system/com.local-agent.celery-worker` and `ps` for
   `celery`/`ollama` on the Mac itself, to confirm live vs. still-hung.
2. From the workstation farm venv: `farm_health --json`, and confirm
   `local_agent.worker_farm.tasks.qwythos_evaluate` is present in
   `registered_tasks`.
3. Only restart if step 1 shows the process is actually dead or step 2
   shows the wrong task list — do not restart reflexively.

Tracked as Task #47 (re-verify Qwythos farm tier once the Mac is back).
