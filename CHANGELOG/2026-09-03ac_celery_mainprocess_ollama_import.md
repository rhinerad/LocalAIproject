# 2026-09-03ac — Celery MainProcess can unpickle ollama_client exceptions

## What

Python source change in `local_agent/worker_farm/tasks.py`. Celery prefork MainProcess now imports `ollama_client` at module load so a worker-raised `OllamaUnavailable` can be unpickled/repr'd instead of crashing the consumer.

Cause of the live `judge_transcript` 60s timeout: not the 120s summarize/Ollama wait. `embed_chunks` raised `OllamaUnavailable` (Ollama down). MainProcess then hit `ModuleNotFoundError: No module named 'ollama_client'` while handling that exception (the class was only imported inside `_embed_chunks` in the fork). Consumer died; Redis `Timeout connecting to server` followed. Live `judge_transcript` itself completed in ~0.035s when the worker was healthy.

Ollama on Louises-MBP is the LaunchDaemon `system/com.local-agent.ollama` at `127.0.0.1:11434`. This changelog does not change that.

## Fix

After `_use_local_agent_imports()` is defined, `tasks.py` now calls it and `import ollama_client as _ollama_client` at module load (what Celery does via `celery_app` `include=`). Per-task `_use_local_agent_imports()` calls are unchanged.

## Tests

From the repository root, farm venv only:

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_tasks_mainprocess_exceptions -v
```

3 tests, OK (~8s):

- repo-root-only `import ollama_client` still fails (`No module named 'ollama_client'`) — original MainProcess layout
- `from local_agent.worker_farm import tasks` then pickle/unpickle `OllamaUnavailable` succeeds
- reloaded `tasks` module has `_ollama_client.OllamaUnavailable`

## Files

- `local_agent/worker_farm/tasks.py`
- `local_agent/worker_farm/test_tasks_mainprocess_exceptions.py`

## Scope

No `outputs/equal_shares/`. No farm/GUI/GPU start on DuranGamingPC. Mac live copy of `tasks.py` and Celery LaunchAgent restart are follow-up on Louises-MBP (same import; do not touch the Ollama daemon).
