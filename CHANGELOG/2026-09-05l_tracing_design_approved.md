# 2026-09-05l — tracing.py design approved, defaults accepted, PR 1 authorized

## Scope

🟠 lane, Task #44. Design review only — no code shipped yet. Design doc
lives at `A:\Users\rhine\AppData\Local\Temp\grok-rhine\grok-design-doc-a1c90b30.md`
(local machine temp path, not in the repo).

## What this is

A structured SQLite span logger (`local_agent/knowledge/traces.db`,
stdlib `sqlite3` only) recording one trace per `agent.answer()` turn, so
investigations like the empty-completion bug and the mug-image mixup
(both required hand-joining hop logs, `router.decide()`, Ollama stderr,
and `comfy_mcp_audit.jsonl`) become a query instead of manual log
correlation. Kill switch `LOCAL_AGENT_TRACING=0` (same polarity as the
timeshare switch). Explicitly out of scope: Phoenix, Langfuse,
LLM-as-judge, OTLP export, a GUI viewer.

Design passed review after 3 rounds (2 critical / 8 major / 8 minor / 3
nit issues addressed cumulatively), 0 open issues remaining.

## Decision: all 4 stated defaults accepted

1. Probe scripts do not import `tools` — JSONL-only for v1.
2. `trace_id` is not published on the route SSE event (would be
   transport-visible and require an `APP_REVISION` bump).
3. Compact-summarizer tokens captured only when easy — not a v1 blocker.
4. `traces.db` / `-wal` / `-shm` gitignored, binding in PR 2.

## PR plan authorized to start

1. `chat_stream` telemetry + hop-loop consumer — `StreamEnd` trailer on
   normal end and cooperative Stop; `agent.py` only appends `str` pieces.
   No `APP_REVISION` bump. **Authorized to start now.**
2. `tracing.py` core, unwired — schema, context manager, dummy span,
   `record_decision`, redaction, `prune()`. Parallel with PR 1.
3. Instrument `agent.answer` — live hop order, farm-before-compact,
   `skip_farm` on route, prune after turn close.
4. MCP audit binary offset — completes the mug-image recipe, no
   `timeshare_log` refs (that WARNING logger was already removed
   2026-09-04aa).
5. Retention hook + CHANGELOG/TODO — mark plan §4a done, §4b still open.

Not PRs: OTLP/Phoenix, LLM-as-judge, GUI viewer, global `tools.call` wrap.

## What was not done

No `tracing.py` file created yet — this was explicitly design-only, per
the report. No production code changed.

## Next

Task #45 (visible agent activity trace in chat UI) remains queued behind
this, per the original task order.
