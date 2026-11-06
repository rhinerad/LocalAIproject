# 2026-08-30 — Worker-farm tests name the one correct invocation

## What changed

Test-harness only. `celery_app.py`, `tasks.py`, `tools/powerinfer/`, `router.py`,
and `work/` were not touched.

- `test_farm_core.py` and `test_termux_powerinfer2_edge_worker.py` refuse
  `python path/to/test_*.py` with exit 2 and the farm-venv `-m unittest`
  command, instead of a bare `ModuleNotFoundError: No module named 'local_agent'`.
- `test_worker_app_registers_the_distill_task` probes Celery first. A PATH
  Python without Celery fails as “you're not running the farm .venv”, not as
  an unregistered `distill_export` task. `MISSING` remains the real
  registration failure.
- `local_agent/worker_farm/README.md` states the one correct invocation at
  the top.

## Before (2026-08-30 reverify)

1. PATH `python local_agent/worker_farm/test_farm_core.py -v` →
   `ModuleNotFoundError: No module named 'local_agent'` (0 tests).
2. PATH `python -m unittest …` → 15/16, failure text
   `AssertionError: 'REGISTERED' != ''` plus `No module named 'celery'`
   in stderr (looked like registration).
3. Farm `.venv` `-m unittest` → 16/16 OK.

## After (this session)

**Case 1** — PATH, run by path, repo root:

```
python local_agent/worker_farm/test_farm_core.py -v
ERROR: local_agent is not importable because this file was run by path.
From the repository root, use the farm venv:
  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
exit=2
```

Same message and exit 2 for `test_termux_powerinfer2_edge_worker.py`.

**Case 2** — PATH `python -m unittest local_agent.worker_farm.test_farm_core
local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v`

```
Ran 16 tests in 9.172s
FAILED (failures=1)
AssertionError: Celery is not installed in this Python environment — you're not running the farm .venv. From the repository root:
  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
```

Not a false pass. Not a registration traceback.

**Case 3** — farm venv, same `-m unittest` command:

```
Ran 16 tests in 16.238s
OK
```

## Docker / Redis

Still unverified. Docker Desktop’s engine is down
(`npipe:////./pipe/dockerDesktopLinuxEngine` missing). Rhine needs to start
Docker Desktop; this session did not.
