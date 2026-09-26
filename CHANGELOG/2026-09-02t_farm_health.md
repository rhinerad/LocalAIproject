# 2026-09-02t — standalone farm_health diagnostic

## What

Added `local_agent/worker_farm/farm_health.py`: a CLI + `check_farm_health(timeout_s=5.0)` helper that reports broker reachable / workers responding / latency_ms without submitting any summarize, embed, judge, or distill job.

## How it checks

1. Loads `local_agent/worker_farm/.env` the same way `_farm_submit_wait._load_env_file` does (does not override already-set env). Broker URL is `FARM_BROKER_URL`.
2. TCP-connects to the host:port from that URL (so the WireGuard hub `10.90.90.1:6379` is checked, not a hardcoded 127.0.0.1). Timeout = `timeout_s`. Connection refused / timeout → `status=unreachable`.
3. If the broker socket answers, Celery `inspect.ping()` (control command, not a queued task) tells whether any worker process is alive. Empty/None ping → `status=no_workers` (broker up, workers down).
4. Any exception is caught, passwords redacted from the error string, and returned in the dict. The function never raises.

Not wired into `agent.py` or `farm_offload.py`.

## CLI

From repository root, farm venv:

```
local_agent\worker_farm\.venv\Scripts\python.exe -m local_agent.worker_farm.farm_health
```

Prints one status line, e.g.

```
broker reachable: yes  workers responding: yes  latency_ms: 18.4  workers: celery@Louises-MacBook-Pro.local
```

`--json` dumps the dict. Exit 0 only when `status=ok`.

## Tests

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_health -v
```

Covers reachable+responsive, unreachable (refused/timeout), and broker-up/worker-down. Celery inspect and TCP are mocked; the suite does not require a live Mac or WireGuard hub.

## Files

- `local_agent/worker_farm/farm_health.py` (new)
- `local_agent/worker_farm/test_farm_health.py` (new)
- `local_agent/worker_farm/README.md` (unittest line + health CLI)
- `TODO.md` (checked item under Phase 1 worker-farm bootstrap)

Celery `inspect.ping()` waits its full timeout even after a reply, so the health check caps inspect wait at 1.0s while TCP still uses `timeout_s` (default 5). A live 2026-09-02 run reported `broker reachable: yes`, `workers responding: yes`, worker `celery@Louises-MBP`.
