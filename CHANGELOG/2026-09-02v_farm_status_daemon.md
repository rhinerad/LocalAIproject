# 2026-09-02v — farm_status.json snapshot daemon

## What

Periodic cheap farm-status snapshot on top of `farm_health.check_farm_health()`. Other code can read `local_agent/worker_farm/farm_status.json` instead of calling Celery `inspect()` live.

Not wired into `agent.py` or `farm_offload.py`.

## farm_health --json

`--json` already existed. It now stamps `checked_at` (UTC ISO-8601) onto the same object `check_farm_health()` returns and prints one JSON object to stdout.

## Daemon

`local_agent/worker_farm/farm_status_daemon.py`

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_status_daemon
```

- Interval default 30s; `--interval` wins, else `FARM_STATUS_INTERVAL_S` (FARM_* env, same family as `FARM_BROKER_URL`).
- Snapshot path default `worker_farm/farm_status.json`; `--path` or `FARM_STATUS_PATH`.
- `--once` writes one snapshot and exits (used to prove a live run).
- Atomic write: temp file in the same directory, `fsync`, then `os.replace`. A crash before rename leaves the previous valid file (or no file), never a truncated dest.
- A failed `check_farm_health()` is written through as `status=unreachable` / `no_workers`; the loop does not die.
- Logs one status line plus `checked_at` per tick.

`farm_status.json` is gitignored.

## farm_status.json shape

```json
{
  "broker_reachable": true,
  "checked_at": "2026-09-02T20:43:00+00:00",
  "error": null,
  "latency_ms": 12.3,
  "status": "ok",
  "workers": ["celery@Louises-MBP"],
  "workers_responding": true
}
```

Keys are stable. `status` is `ok` | `unreachable` | `no_workers` | `unconfigured`.

## Tests

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_status_daemon -v
```

## Files

- `local_agent/worker_farm/farm_status_daemon.py` (new)
- `local_agent/worker_farm/test_farm_status_daemon.py` (new)
- `local_agent/worker_farm/farm_health.py` (`with_checked_at`, `--json` stamp)
- `local_agent/worker_farm/README.md`
- `local_agent/worker_farm/.gitignore`
- `TODO.md`

Renamed 2026-09-02 from `u_` to `v_` because `2026-09-02u_compaction_prefetch.md` already held that letter (parallel agents, no shared allocation).
