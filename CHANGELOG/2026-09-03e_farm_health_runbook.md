# 2026-09-03e — farm health datapath runbook

Docs only; no Python changed.

## What changed

- New `docs/FARM_HEALTH_RUNBOOK.md`: 2026-09-03 2am checklist from the 2026-09-02 evening through ~2:55 AM ET datapath outage (interface-up ≠ datapath, registered-task line, WireGuard owner conflict, LaunchDaemon bash 3 vs 4). Reboot persistence is not confirmed.
- `local_agent/worker_farm/README.md`: one pointer line to that runbook under `farm_health` (CLI docs already existed).

## Why

`farm_health` is a diagnostic, not a gate. Tonight the hub and Mac VPN UI looked Connected while Redis/SSH/ICMP over `10.90.90.0/28` were dead. Operators need the live CLI sequence, not a stale `farm_status.json`.

## Evidence

Live CLI still prints `format_status_line` then `format_registered_line`; `--json` includes `registered_check`. Exit 0 only when connectivity status is `ok`.

## Verified after

Wrote the files; confirmed the README insert is a single new line and no other docs were overwritten.

## Still unverified

Reboot persistence of the LaunchDaemon-owned `utun5` datapath.
