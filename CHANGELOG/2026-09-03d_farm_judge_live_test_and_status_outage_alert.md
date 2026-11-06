# 2026-09-03d — live judge integration test and farm-status outage alert

## What

Two worker-farm changes, both inside `local_agent/worker_farm/` (plus this changelog):

1. Live integration tests now submit a real `judge_transcript` task, matching the existing summarize/embed pattern.
2. `farm_status_daemon` logs a greppable `FARM_STATUS_OUTAGE` line after N consecutive failed health checks.

Not wired into `agent.py` or `farm_offload.py`. No new dependencies. Daemon is not installed as a service.

## Live judge coverage

`local_agent/worker_farm/test_farm_integration.py` (still omitted from the fast suite):

- New test `test_judge_transcript_returns_real_result` submits `local_agent.worker_farm.tasks.judge_transcript` on the `judge` queue via the same `_send_live_task` helper.
- Envelope: `{"chat_id": "farm-integration-judge", "messages": [{"role": "user", "content": "What is 2+2?"}, {"role": "assistant", "content": "4"}]}`.
- Timeout 60s. Asserts the mechanical rubric result shape (`chat_id`, `message_count`, `finding_count`, `findings`, `by_rule`, `status` in `no_findings` / `review_required`).
- Skip (do not fail) if `check_farm_health` status is not `ok` — same `setUp` skip as summarize/embed.
- Existing `test_registered_tasks_include_summarize_and_embed` now also `assertIn` `judge_transcript`. Summarize/embed assertions are unchanged.

## Consecutive-failure alerting

`local_agent/worker_farm/farm_status_daemon.py`

A failed check is whatever `check_farm_health` already treats as not healthy: any snapshot whose `status` is not `ok` (`unreachable`, `no_workers`, `unconfigured`, …). No second health definition.

- N default 3. CLI `--fail-alert-after` wins, else env `FARM_STATUS_FAIL_ALERT_AFTER`, else 3 (same CLI-over-env pattern as `--interval` / `FARM_STATUS_INTERVAL_S`).
- Policy: log `FARM_STATUS_OUTAGE` when the consecutive count first reaches N, then again every N failures thereafter (heartbeat). Counter resets on `status=ok`. If an outage had been declared, the first healthy check also prints `FARM_STATUS_RECOVERED`.
- Example line:

```
FARM_STATUS_OUTAGE consecutive_failures=3 status=unreachable error=ConnectionRefusedError: timed out
```

No email, Slack, toast, or webhook.

## Tests

Fast (mocked, no live farm):

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_health local_agent.worker_farm.test_farm_status_daemon -v
```

29 tests, OK (5.841s). New daemon tests cover N config, greppable line format, crossing N, heartbeat every N, reset without recovered, recovered after outage, `unconfigured` as failed, and run_loop stdout.

Live (slow; skip is success if unreachable):

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v
```

4 tests, OK (skipped=4). Broker reachable; no worker answered ping (`status=no_workers`). Skip reason: `live farm unreachable (no_workers): broker reachable, no worker answered ping`. Includes the new judge test.

## Files

- `local_agent/worker_farm/test_farm_integration.py`
- `local_agent/worker_farm/farm_status_daemon.py`
- `local_agent/worker_farm/test_farm_status_daemon.py`
- `local_agent/worker_farm/README.md`
