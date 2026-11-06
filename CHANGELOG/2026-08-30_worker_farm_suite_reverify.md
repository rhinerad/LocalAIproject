# 2026-08-30 — Worker-farm suite re-verified (not trusted from 2026-08-29)

## What this is

A fresh re-run of the two suites cited as 16/16 in
`CHANGELOG/2026-08-29_worker_farm_live_sample.md`. No farm source was changed.
`tools/powerinfer/`, `router.py`, and `work/` were not touched.

## Actual current counts

From repository root
`COMFYUI_STORY_HANDOFF_2026-08-09/`:

**1. `python local_agent/worker_farm/test_farm_core.py -v` and
`python local_agent/worker_farm/test_termux_powerinfer2_edge_worker.py -v`
using PATH Python 3.12.10**

Both files abort at import: `ModuleNotFoundError: No module named 'local_agent'`.
`local_agent/` has no `__init__.py`; running the files by path puts
`local_agent/worker_farm/` on `sys.path`, so the `from local_agent.worker_farm...`
imports cannot resolve. **Collected tests: 0. This is not 16/16.**

**2. `python -m unittest local_agent.worker_farm.test_farm_core
local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v`
same PATH Python 3.12.10**

```
Ran 16 tests in 3.750s
FAILED (failures=1)
```

15 passed. The only failure is
`test_worker_app_registers_the_distill_task`. The subprocess it starts
(`sys.executable -c` + Celery `find_app('local_agent.worker_farm.celery_app:app')`)
dies with `ModuleNotFoundError: No module named 'celery'`. PATH Python has no
Celery; `import celery` fails in that interpreter.

That is not a silent `distill_export` unregistration. The probe never reached
`app.tasks`. `celery_app.py` still constructs Celery with
`include=["local_agent.worker_farm.tasks"]` when Celery is installed.

**3. Isolated farm venv (what `START_PHASE1_CPU_WORKER.ps1` actually launches)**

`local_agent/worker_farm/.venv/Scripts/python.exe` — Celery 5.6.3.

```
python -m unittest local_agent.worker_farm.test_farm_core
    local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
Ran 16 tests in 19.094s
OK
```

Including `test_worker_app_registers_the_distill_task` → `REGISTERED`.
Termux contract tests 3/3.

## Diagnosis

The 2026-08-29 “16/16 from the repository root” claim is true **only** when
the isolated worker venv is the interpreter and the tests are loaded as
packages (`python -m unittest ...` from the repo root). It is not true of
PATH `python` running the files by path. That matches the Phase 1 foundation
note that launchers must not use whichever global Python is first on PATH.

No farm logic was patched to make the default-Python run green.

## Docker / Redis live launcher

Not re-run. `docker version` / `docker ps` failed:

`failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine`

Docker Desktop’s engine is not up for this account. Per the request, the
guarded broker launcher was not forced. Credential-path prepend and
`REDIS_PASSWORD` health-check Compose changes remain unverified on a live
`healthy` 127.0.0.1:6379 this session.

## Still unverified

- `START_PHASE1_BROKER.ps1` reaching `healthy` on 127.0.0.1:6379.
- A live Celery worker + benign distill sample on this engine.
