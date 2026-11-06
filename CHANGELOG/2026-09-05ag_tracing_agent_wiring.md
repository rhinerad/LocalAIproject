# 2026-09-05ag — Wire tracing.py into agent.answer() (PR 3)

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05ag**.

Tracing design PR 3. `agent.answer()` now opens spans using the PR 2 leaf
module. `LOCAL_AGENT_TRACING=0` still completes the turn identically.
MCP audit binary offset (PR 4) was not touched. APP_REVISION unchanged.

## What is wired

- `kind=turn` around the whole call (inside `@_chat_busy_guard`).
  Short-circuits and early returns still get a turn span
  (`short_circuit=action_resolver`, `early_return=access_bypass` / etc.).
- `kind=route` around **real** `router.decide()` calls: pre-loop hop-0
  `/free`, per-hop when not reusing hop0, farm `skip_farm=True` fallback,
  empty-completion retry, 14B→8B `fallback_after_primary_failure`.
  Hop-0 reuse is a hop attribute (`reused_hop0_route`), not a fake route span.
- `record_decision()` allow-list only — never `Decision.as_dict()` into the DB.
- Live hop order: farm `reason` (Qwythos) **before** compact; local
  `chat_stream` `reason` only if `not farm_handled`. Tokens from `StreamEnd`.
- `kind=tool` around `_execute_plan` / hop `run_one` (parent=hop for pool
  workers). Not a global `tools.call` wrap.
- Empty-completion retry is a **new hop** with `retry_reason=empty_completion`
  and `skip_farm=true` on that hop's route.

## Empty-completion join (reconstructed)

No live Ollama. Same 2026-09-04r shape: thinking-only `StreamEnd` then retry
still empty → `_EMPTY_COMPLETION_REPLY`.

Design-doc SQL against the temp DB:

| hop | reused_hop0 | retry_reason | host | skip_farm | tokens_out | visible | thinking | think |
|---|---|---|---|---|---|---|---|---|
| 0 | 1 | empty_completion | 127.0.0.1:11435 (from pre-loop route COALESCE) | NULL | 838 | 0 | 200 | 0 |
| 1 | NULL | empty_completion | 127.0.0.1:11435 | 1 | 637 | 0 | 10 | 0 |

Turn `output_summary` is the guard sentence, never `""`. `knowledge/traces.db`
was not created.

## Tests

```text
python -m unittest test_agent_tracing test_tracing test_native_tool_calling test_agent_timeshare_gpu_gate -q
```

98/98 OK. Kill-switch test: same empty-completion reply with tracing=0 and
no DB file. Occupancy/process lists do not appear in the DB.

## Files

- `local_agent/agent.py` (instrumentation)
- `local_agent/tracing.py` (`_maybe_prune`; unittest does not write the
  default DB unless `LOCAL_AGENT_TRACES_DB` is set)
- `local_agent/test_agent_tracing.py` (new)
- `local_agent/test_native_tool_calling.py` (setUp forces tracing=0)
- `TODO.md`

## Scope

No PR 4 MCP JSONL offset. No APP_REVISION bump. No Phoenix. No
`outputs/equal_shares/`. GUI not started.
