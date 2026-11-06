# 2026-09-02 — native tool-calling regression re-run: 57/57 pass

## Scope

Operator said GO for first-bot CPU. Re-ran the stdlib unittest
`local_agent.test_native_tool_calling` from the repository root on
DuranGamingPC. CPU-only mocks; no model download, no GPU, no live Ollama.
Did not do Phase 2 RAG work.

## Command

From repo root, with `PYTHONIOENCODING=utf-8`:

```
python -m unittest local_agent.test_native_tool_calling -v
```

Interpreter (Windows Python 3.12, **not** the farm venv at
`local_agent\worker_farm\.venv`):

`A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe`

Python 3.12.10 (`MSC v.1943 64 bit (AMD64)`). `sys.prefix` is
`A:\Users\rhine\AppData\Local\Programs\Python\Python312`.

## Result

**Ran 57 tests in 7.669s — OK** (57 passed, 0 failed, 0 errors, 0 skipped).
Exit code 0.

Did not use `local_agent\worker_farm\.venv`.
