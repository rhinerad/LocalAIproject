# 2026-09-05ds — Pre-Qwythos proposal route + hop display

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ds**.

Second half of `CHANGELOG/2026-09-05cw_hop_index_and_pre_qwythos_route_scope.md`,
unblocked by Red's Qwythos loop fix `2026-09-05dl`. Hop-index **emit
wrapper** was not on disk in this round (`current_hop` / `_with_hop`
absent in `agent.py`; no hop-index CHANGELOG). GUI hop grouping follows
cw's wire spec: optional integer field **`hop`** on JSON SSE kinds
(`route` / `progress` / `tool`); `hop_index` accepted as an alias.
Text kinds (`tool_result` / `token` / `note`) unchanged. No `trace_id`.
`try_qwythos_on_farm(...)` call, timeout, and skip_farm fallback are
byte-identical.

## What shipped

Before the blocking Mac wait, when `route.backend == "farm"`:

1. `progress` `{stage: "decide", label: "Waiting on Mac Qwythos"}`
2. `route` with `source: "proposal"`, `reason: "attempting farm"`
   (never “Mac accepted”)

Then the existing `try_qwythos_on_farm` wait. After the wait, the
existing `emit("route", as_dict())` remains the **observation** stamp
(farm success: same farm dict; miss: skip_farm local GPU/CPU + fallback
`note`).

`activity_from_sse` treats `source=proposal` routes as
`state=announced` / `source=proposal` / label `attempting farm`.
Unmarked routes stay observation. Optional `hop` is copied onto
persisted cards.

GUI: proposal farm routes do **not** rewrite the who-line (that would
look like proof). Cards stamp “Proposal — not proof of execution”.
If `hop` is present, cards get `data-hop` and a `hop N` label.

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-farm-attempt-route-r81`.

## Tests

```
python -m unittest test_activity_trace test_launcher_revision \
  test_native_tool_calling.NativeToolTests.test_farm_decision_sends_meta_schemas_to_qwythos \
  test_native_tool_calling.NativeToolTests.test_farm_attempt_emits_proposal_route_before_qwythos_wait \
  test_native_tool_calling.NativeToolTests.test_farm_miss_emits_local_observation_route_after_wait -v
```

32/32 OK.

- Success: `on_event` sees progress + proposal farm route **inside**
  the mocked `try_qwythos_on_farm` (wait has started), then a later
  observation farm `route` without `source=proposal`.
- Miss (`None` from Qwythos): same proposal farm route before wait,
  then observation `backend=ollama` local route and the existing
  “falling back locally” note.

## Files

- `local_agent/agent.py`
- `local_agent/server.py`
- `local_agent/static/index.html`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_activity_trace.py`
- `local_agent/test_native_tool_calling.py`
- `TODO.md`
