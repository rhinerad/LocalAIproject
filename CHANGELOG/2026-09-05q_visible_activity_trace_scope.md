# 2026-09-05q — Visible agent activity trace: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05q**.

Task #45. Design note only — no GUI, SSE, or `APP_REVISION` change.

Doc: `docs/design_notes/VISIBLE_AGENT_ACTIVITY_TRACE_2026-09-05.md`.

## Finding

The chat UI already streams `route` / `progress` / `tool` / `tool_result` /
`note` / `queued` / `done` over the existing `on_event` SSE path
(`agent.py` `emit`, `server.py` `push`, `index.html` `stream()`). The
who-line `agent · GPU · {model}` is the `route` event. Almost none of
that is restored after refresh (`openChat` renders `m.content` only).
Hop index is never emitted. Farm Qwythos runs **before** `emit("route")`,
so a cold farm load is silent in the UI.

**Orange `tracing.py` PR 2 does not block this.** Tracing is a SQLite
investigator log; its own design forbids `trace_id` on the `route` SSE
event and lists a GUI viewer as a non-goal. Live cards should keep using
SSE + optional `store.append` meta (`tool_evidence` already exists and is
ignored by the GUI).

No production code changed.
