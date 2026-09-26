# 2026-09-05m — Stop discarding hop-loop token counts (`chat_stream` StreamEnd)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05m**.

`chat()` already copies Ollama `eval_count` / `prompt_eval_count` /
`total_duration` / `eval_duration` (`CHANGELOG/2026-09-03ap`). The hop loop
uses `chat_stream()`, which still dropped those fields from the final
`done=True` NDJSON chunk. Empty-completion hops (2026-09-04r) never yield a
`ToolCall`, so attaching telemetry only to `ToolCall` would still leave those
turns blind.

This is tracing design PR 1 (`grok-design-doc-a1c90b30`). No SQLite span
logger yet. Tracing/token-ledger is still not wired.

## What changed

- New `ollama_client.StreamEnd` trailer on the **Ollama** `chat_stream` path:
  `telemetry` (same four keys as `chat_telemetry()`), `thinking_chars`,
  `visible_chars`. Always last. Yielded on normal completion **and**
  cooperative Stop (best-effort counts from the last parsed chunk). Never
  yield `ToolCall(calls=[])` as a trailer.
- PowerInfer `yield from` is unchanged: **no** `StreamEnd`.
- `agent.py` hop loop only `buf.append` / `emit("token")` for
  `isinstance(piece, str)`; stashes `StreamEnd`; keeps `ToolCall` as today.
  A third yield type must not stringify into stored replies (decision #8).
- `chat()` unpacking unchanged. `APP_REVISION` unchanged.

## Tests

From `local_agent/`:

```text
python -m unittest test_ollama_chat_telemetry test_native_tool_calling test_powerinfer_chat_route test_ollama_context_options -q
```

96/96 OK (~18.6s). `test_ollama_chat_telemetry` is 7/7 (four new stream
tests: done-chunk telemetry, Stop trailer, empty-completion trailer, tool
calls then StreamEnd). Native-tool `list(chat_stream)` assertions updated;
`test_stream_end_is_not_stored_as_text` confirms `agent.answer()` does not
persist `StreamEnd(...)`. PowerInfer still `["ok"]` with no trailer.

## Files

- `local_agent/ollama_client.py`
- `local_agent/agent.py` (yield-type guard only)
- `local_agent/test_ollama_chat_telemetry.py`
- `local_agent/test_native_tool_calling.py`
- `TODO.md` (tracing still unwired; `chat_stream` telemetry captured)

## Scope

No `outputs/equal_shares/`. No `tracing.py`. No APP_REVISION bump. GUI not
started. Empty-completion investigation is **not** complete until PR 3 copies
`thinking_chars` onto the reason span. PR 2 (`tracing.py` core, unwired) can
land in parallel with this.
