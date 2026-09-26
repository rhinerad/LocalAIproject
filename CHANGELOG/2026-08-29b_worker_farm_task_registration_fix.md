# 2026-08-29 — worker_farm: distill_export was never registered on the real worker process

## Context

Found while re-reading `local_agent/worker_farm/*.py` to match existing patterns
before adding a new smoke-test task the same way. Before copying the pattern,
checked whether the existing one actually works end to end, rather than
assuming it does.

## Root cause

`worker.py` launches the real worker as:

```
celery -A local_agent.worker_farm.celery_app:app worker --queues ... --pool ...
```

That `-A` target only ever imports `celery_app.py`. `celery_app.py` builds the
`Celery(...)` app with no `include=` and no `autodiscover_tasks()`. `tasks.py`
(which defines `distill_export` behind `@app.task(...)`) is imported by
`submit_distillation.py` and by the test suite, but **never by the worker
process itself** — and `submit_distillation.py` dispatches by name via
`app.send_task("local_agent.worker_farm.tasks.distill_export", ...)`, not
`.delay()`, so the submitter succeeds and returns a task ID regardless of
whether the worker actually knows that task. `local_agent/worker_farm/__init__.py`
is a docstring only, so package import doesn't pull `tasks.py` in either.

Net effect: `RUN_PHASE1_SAMPLE.ps1` would appear to queue successfully, and the
worker would silently discard every job with Celery's standard "Received
unregistered task" behavior. Nothing in the existing 12-test suite caught this
— all of it tests task-body logic directly (`tasks._run_distill(...)`) or
patches `submit_distillation.app`, never the worker's actual app-loading path.

## Verification

No live Redis was available in this sandbox, and none was needed — task
registration is decided entirely by Python import wiring, before any broker
connection is opened. Copied `celery_app.py`, `tasks.py`, `worker.py`,
`farm_core.py`, `job_registry.py`, `status.py`, `doctor.py`, `submit_distillation.py`,
and `test_farm_core.py` into an isolated sandbox tree, installed `celery==5.6.3`
and `cryptography` fresh, and used Celery's own `celery.app.utils.find_app`
(the exact function the `-A` flag resolves through) plus
`app.loader.import_default_modules()` (the exact call `celery worker` makes
during startup, before consuming) to reproduce the real load path without a
broker:

**Before fix** — `Celery(broker=..., backend=...)`, no `include=`:
```
registered tasks: ['celery.accumulate', 'celery.backend_cleanup', 'celery.chain',
'celery.chord', 'celery.chord_unlock', 'celery.chunks', 'celery.group', 'celery.map',
'celery.starmap']
distill_export registered: False
```

**After fix** — `include=["local_agent.worker_farm.tasks"]` added:
```
registered tasks: [..., 'local_agent.worker_farm.tasks.distill_export']
distill_export registered: True
```

Confirmed the `include=` list itself is not read eagerly at app-construction
time (so `celery_app.py`'s docstring promise — "importing this module never
starts a broker or worker" — still holds): right after `find_app()`,
`distill_export` is absent; it only appears after `import_default_modules()`
runs, matching real worker startup order.

## Changes

### `local_agent/worker_farm/celery_app.py`

Added `include=["local_agent.worker_farm.tasks"]` to the `Celery(...)`
constructor in `create_app()`. This is Celery's standard mechanism for a
worker to lazily pull in a sibling task module by dotted path instead of a
top-level `import` — which was not an option here anyway, since `tasks.py`
already does `from .celery_app import app` and a direct top-level import in
the other direction would be circular.

### `local_agent/worker_farm/test_farm_core.py`

Added `test_worker_app_registers_the_distill_task`, imports `os`, `subprocess`,
`sys`. It shells out to a fresh interpreter (mirroring what `worker.py` itself
does) that resolves the app exactly as `-A local_agent.worker_farm.celery_app:app`
would, runs `import_default_modules()`, and asserts `distill_export` is
registered. A subprocess is required, not optional: this test module already
imports `local_agent.worker_farm.tasks` at file scope for the existing tests,
which caches it in `sys.modules` with `app=None` (no `FARM_BROKER_URL` set at
that point). An in-process retry against a freshly-constructed app would hit
that stale cache and silently no-op instead of re-registering — which would
have made the regression test pass regardless of whether the real bug was
fixed. Caught this by running the first version of the test against the
already-fixed code and watching it fail for the wrong reason.

Negative-control run (reverted `include=` in the sandbox copy only, real
project file untouched): the new test fails with `'REGISTERED' != 'MISSING'`.
Restored the fix: passes. Full suite: 13/13 (12 pre-existing + 1 new).

## What is unverified

This was proven against an isolated sandbox copy running `celery==5.6.3`
installed fresh, not against the project's actual `local_agent/worker_farm/.venv`
on the Windows machine, which may pin a different Celery version — `include=`
is core, stable Celery behavior across the 4.x–5.x line, so this is low risk,
but the closing step is still to run
`.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core -v`
from that real environment and confirm 13/13 there. No broker was started; this
is import-wiring verification only, not a live end-to-end submit → worker →
result run. That live run still needs Docker Desktop's engine confirmed
running and should happen from the normal Windows desktop account per the
existing Phase 1 foundation note.
