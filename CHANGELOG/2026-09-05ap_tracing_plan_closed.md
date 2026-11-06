# 2026-09-05ap — tracing.py plan fully closed (PR 4 shipped)

## Scope

🟠 lane, Task #44's underlying build. Reviews Grok's own report
(`2026-09-05ak`, already checked off in TODO.md). No new work.

## What shipped

`_comfy_audit` now writes binary-mode JSONL (`"ab"`), captures `tell()`
before the line, and best-effort links the current span to it —
`ref_kind=comfy_mcp_audit`, `ref_target=runtime/comfy_mcp_audit.jsonl#{offset}`,
plus `prompt_id`/`mcp_status`/`caller_file`. Only the pointer lives in
`traces.db`; the actual generate prompt, full caller dict, and raw MCP
payload stay in the JSONL file only — exactly the pointer-not-copy rule
from the original design. A JSONL write failure still correctly raises
`ToolError` (that's a real audit-trail failure); a `link()` failure is
merely logged and cannot fail a generate that already succeeded at MCP
(tracing must never break a working turn).

## The motivating case, actually proven

The mug-image mixup (desktop generate vs. a VRAM-probe sharing a
filename) was the original justification for this entire tracing
project. It was reconstructed end-to-end: a mocked `comfy_generate` on a
real traced turn produced a `span_refs` row with the right
`conversation_id`, `hop_index`, `prompt_id`, and `caller_file`, and
seeking to that row's byte offset in the JSONL file landed on the exact
line with that prompt — while the prompt token itself was confirmed
absent from `traces.db`. That's the query-instead-of-manual-log-join
outcome the whole plan was built for.

49/49 + 88/88 tests pass across the relevant suites, including link
failure not blocking a successful generate, and prompt content confirmed
never copied into the database.

## Plan closed, in full

All four PRs shipped: `2026-09-05m` (StreamEnd telemetry), `2026-09-05y`
(SQLite core), `2026-09-05ag` (agent.answer wiring), `2026-09-05ak` (MCP
audit pointer). `TODO.md`'s `local_agent/tracing.py` item is `[x]`.
Explicitly still out of scope, as originally planned: OTLP/Phoenix
export, and the separate LLM-as-judge item (§4b) — which shipped
independently as its own project (`2026-09-05af`/`aj`).

## Status

Task #44 fully closed end-to-end: scoped, built across 4 PRs, and the
original motivating bug is now demonstrably a query, not a manual log
correlation exercise.
