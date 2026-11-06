# 2026-09-05ak — MCP audit binary offset linked into traces (PR 4)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05ak**.

Last PR in the `tracing.py` plan. Completes the mug-image investigation
recipe: hop/tool span → `span_refs` byte offset → one JSONL line in
`runtime/comfy_mcp_audit.jsonl`. The generate prompt stays in JSONL only.

No `timeshare_log` refs (WARNING logger was removed in `2026-09-04aa`).
No APP_REVISION bump. Phase B Phoenix/OTLP not built.

## What is wired

`_comfy_audit` now:

1. Opens the JSONL as binary append (`"ab"`).
2. `offset = fh.tell()` **before** writing the UTF-8 line.
3. After a successful write, best-effort `tracing.current_span().link(
   "comfy_mcp_audit", target="runtime/comfy_mcp_audit.jsonl#{offset}",
   extra={prompt_id, mcp_status, caller_file})`. `link()` is in-memory;
   SQLite flush is on the tool span `__exit__`.
4. JSONL `OSError` still raises `ToolError`. A tracing/link failure is
   logged and **cannot** fail a generate that already succeeded at MCP.
5. `tools.last_comfy_audit()` → `(offset, prompt_id, caller_file)` for
   tests / probes. Not the model-visible tool result.

Direct `tools.comfy_generate` callers (VRAM probes) still write JSONL
and get no turn span — same finding as `2026-09-04t`.

## Mug-image join (reconstructed traced turn)

Mocked `comfy_generate` during `agent.answer()` for chat
`7d474ba55d244abe`, prompt token `UNIQUE_MUG_PROMPT_TOKEN_7d474ba55d244abe`.

SQL:

```sql
SELECT t.conversation_id, s.name, s.hop_index, ref.ref_offset,
       json_extract(ref.ref_extra,'$.prompt_id'),
       json_extract(ref.ref_extra,'$.caller_file')
FROM spans s
JOIN spans t ON t.trace_id=s.trace_id AND t.kind='turn'
JOIN span_refs ref ON ref.trace_id=s.trace_id AND ref.span_id=s.span_id
WHERE s.kind='tool' AND s.name='comfy_generate'
  AND ref.ref_kind='comfy_mcp_audit';
```

Result: `conversation_id=7d474ba55d244abe`, `hop_index=0`,
`prompt_id=mug-prompt-id`, `caller_file` ending in `agent.py`.
`fh.seek(offset)` on the JSONL returns that prompt. The unique token is
**not** in `traces.db`.

## Tests

```text
python -m unittest test_comfy_tools test_agent_tracing test_tracing -q
python -m unittest test_native_tool_calling -q
```

49 + 88 OK. New: binary seek roundtrip, prompt not copied into traces.db,
link failure does not fail generate, mug-image join through `agent.answer()`.

## Files

- `local_agent/tools.py`
- `local_agent/test_comfy_tools.py`
- `local_agent/test_agent_tracing.py`
- `TODO.md` (tracing.py item checked)
- `LLMOPS_AUDIT.md` (§4a Phase A status)

## Scope

No `timeshare_log`. No APP_REVISION. No Phoenix. No `outputs/equal_shares/`.
GUI not started. `operator_eval.py` LLM-as-judge (§4b) remains open.
