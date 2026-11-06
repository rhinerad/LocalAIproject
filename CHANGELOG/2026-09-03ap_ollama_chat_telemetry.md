# 2026-09-03ap — Stop discarding Ollama token/duration telemetry

Date: 2026-09-03. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-03ap** (letters through `ao` on disk; claim unique).

`LLMOPS_AUDIT.md` (2026-09-02) flagged that `ollama_client.py::chat()` already receives `eval_count`, `prompt_eval_count`, `total_duration`, and `eval_duration` from Ollama's `/api/chat` response and throws them away, returning only `(text, tool_calls)`. That was the one ungated code change in that doc (SQLite tracing and judge-scoring stay proposals).

## What changed

`chat()` now copies those four fields onto the return value. The result is still a 2-tuple, so existing `text, calls = chat()` sites are unchanged. The same object also has `.telemetry` (a dict of the four keys when present). Helper `chat_telemetry()` does the copy so later tracing/token-ledger work does not have to re-parse the raw response.

PowerInfer proxy turns still return empty telemetry — that path is not Ollama `/api/chat` and does not have these fields.

No SQLite span logger, no judge pre-score, no new dependency, no GUI/GPU/farm start.

## Tests

From `local_agent/`:

```text
python -m unittest test_ollama_chat_telemetry test_native_tool_calling.NativeToolTests.test_chat_passes_tools test_native_tool_calling.NativeToolTests.test_chat_passes_explicit_keep_alive test_native_tool_calling.NativeToolTests.test_chat_passes_json_schema_format test_ollama_context_options -v
```

7/7 OK (~0.002s): the four fields are captured and extra/non-numeric keys are omitted; existing 2-tuple unpacking still works.

## Files

- `local_agent/ollama_client.py`
- `local_agent/test_ollama_chat_telemetry.py`
- `TODO.md` (LLMOps `chat()` item marked done; tracing and judge pre-score stay open)

## Scope

No `outputs/equal_shares/`. APP_REVISION unchanged. GUI not started. SQLite tracing and LLM-as-judge scoring were not built — still proposals in `LLMOPS_AUDIT.md`.
