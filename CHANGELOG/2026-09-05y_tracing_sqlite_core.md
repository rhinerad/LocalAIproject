# 2026-09-05y — tracing.py SQLite span logger core, unwired

Date: 2026-09-05. Host: DuranGamingPC. All times America/New_York (UTC-4).

Id from `python scripts/next_changelog_id.py` immediately before write: **2026-09-05y**.

Tracing design PR 2. Leaf module: **zero** imports of `agent` / `router` /
`tools` / `artifacts` / `ollama_client`. Does not reference `StreamEnd`
(that binding is PR 3). Does **not** wrap `agent.answer()`.

## What changed

- New `local_agent/tracing.py`: stdlib `sqlite3` span logger at
  `knowledge/traces.db` (override `LOCAL_AGENT_TRACES_DB`). WAL,
  `timeout=10`, `isolation_level=None`, `PRAGMA foreign_keys=ON`,
  per-write connection, `BEGIN IMMEDIATE` — copied from
  `worker_farm/job_registry.py`.
- Schema: `spans` + `span_refs` + `schema_meta` (`schema_version=1`).
  Kinds: `turn|hop|route|reason|tool|retrieval|compact|action`.
- Context manager `span()` with dummy/no-op span on kill-switch, bad
  kind, or insert failure. Body exceptions re-raise after flush.
  `link()` is in-memory only; refs INSERT on `__exit__`.
- `record_decision()` allow-list: tier/host/model/reason/backend/gpu_busy/
  capability/profile/skip_farm/timeshare.path|outcome|clear_vram.ok.
  Never `Decision.as_dict()`. Occupancy/process lists stay out.
- `summarize_text()` truncate/hash (`SUMMARY_LIMIT=800`); copies existing
  `artifact_id=` pointers. Never calls `artifacts.store`.
- `summarize_tool_args()` → `ToolArgSummary` (keys + sha256 + json_bytes +
  truncated path/clip/action/name). Same shape as `_redact_args`, copied
  rather than imported.
- `prune()`: whole-trace age delete (14d) and cap (50k → 80%). Never VACUUM,
  never unlinks the DB.
- Kill switch `LOCAL_AGENT_TRACING=0` (unset = on), same polarity as
  timeshare. `enabled()` re-reads env per call. `reset_for_tests()` clears
  `_BROKEN` and the TLS stack.
- Gitignore: `local_agent/knowledge/traces.db`, `-wal`, `-shm`.

## Tests

From `local_agent/`:

```text
python -m unittest test_tracing -q
```

15/15 OK. Suite default is `LOCAL_AGENT_TRACING=0`; tests that write enable
explicitly against a temp DB. `knowledge/traces.db` is not created.

## Files

- `local_agent/tracing.py` (new)
- `local_agent/test_tracing.py` (new)
- `local_agent/knowledge/.gitignore` (new)
- `TODO.md`

## Scope

No `agent.answer()` wiring (PR 3). No MCP audit binary offset (PR 4).
No APP_REVISION bump. No Phoenix. No `outputs/equal_shares/`. GUI not started.
