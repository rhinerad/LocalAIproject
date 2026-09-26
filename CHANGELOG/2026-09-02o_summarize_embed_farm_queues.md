# 2026-09-02 — worker farm: summarize/embed queue code (not yet live)

## Scope

Operator asked whether the worker farm is ready to start helping the local
agent. Answer given: partially — transport is proven, but the specific
task code didn't exist and the connected worker has no LLM installed.
Operator chose to have the task code written now, deployment deferred.
Implements `HARNESS_OPTIMIZATION.md` §4a.

## What was built

`local_agent/worker_farm/tasks.py`:
- `_summarize_messages(messages)` / `_embed_chunks(chunks)` — helper
  functions that lazily add `local_agent/`'s own directory to `sys.path`
  before importing `context_compactor`/`ollama_client`/`router` (those
  modules use flat imports like `from atomic_io import ...`, matching how
  `agent.py` runs them — not guaranteed to already be on `sys.path` in a
  worker process launched fresh on a secondary machine). Same defensive
  pattern `tools.py`'s `forget_fact()` already uses elsewhere in this repo.
- `summarize_conversation` Celery task — envelope `{"messages": [...]}`,
  calls `context_compactor.summarize_old_messages`. Reports
  `{"summarized": false, "note": "..."}` if the local model isn't
  installed/reachable, rather than raising — this is the expected first
  state on a fresh worker, not an error.
- `embed_chunks` Celery task — envelope `{"chunks": [{"id","text"}]}`,
  calls `ollama_client.embed` against the worker's own `router.CPU_HOST`.
  Deliberately stateless: returns `{id: vector}` only, does not read or
  write `retrieval.py`'s on-disk embedding cache — merging results into
  that cache is left for a workstation-side caller, not written here.

`local_agent/worker_farm/celery_app.py`: registered `summarize` and
`embed` `KombuQueue`s. **Added to both `task_queues` and `task_routes`
together**, with an explicit code comment — this is exactly the bug found
and fixed for the `judge` queue earlier this session (in `task_routes` but
not `task_queues`, so Kombu silently mismatched the exchange and jobs
never reached a worker until it was caught).

## Tests — written, NOT executed

Added to `local_agent/worker_farm/test_farm_core.py` (existing file, same
pattern as its `judge_transcript` test block): a subprocess-based
registration check confirming both tasks *and* both queues are present
(the same check that would have caught the `judge` bug), envelope
validation tests for both tasks, a mocked success-path test for each, and
a specific test for `summarize_conversation`'s graceful
model-not-installed result.

**Not run.** These live in the `worker_farm` test suite, which requires
the isolated farm virtualenv (`local_agent\worker_farm\.venv\Scripts\
python.exe`, not plain `python`) with `celery` installed — different from
the `local_agent/test_*.py` suite already verified earlier this session.
Command to run, from the repo root:
```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core -v
```

## Why this isn't "the farm is helping the agent yet"

Confirmed still true, restated so it isn't lost: neither queue can do
useful work on `mac_worker` (or any currently-connected machine) because
no worker has Ollama or the relevant model installed yet
(`worker_farm/README.md`'s "known worker machines" table already recorded
this gap earlier today). `summarize_conversation` will just report
"not installed" every time until that changes; `embed_chunks` will error.
Also not built: the ACL re-grant for the new queues, deployment of the
updated files to the Mac, a worker restart, and any code in `agent.py`
that actually decides to use these queues instead of running locally —
none of that was in scope for this pass (file-edit-only session, no
SSH/bash access).

## What was not done

No SSH into the Mac, no Ollama install, no ACL script run, no `agent.py`
changes, no real end-to-end test against a live broker.
