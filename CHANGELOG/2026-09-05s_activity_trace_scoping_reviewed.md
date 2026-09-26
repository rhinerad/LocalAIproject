# 2026-09-05s — Visible agent activity trace: scoping reviewed, v1 build authorized pending operator go

## Scope

🟣 lane, Task #45. Reviews Grok's own scoping pass
(`docs/design_notes/VISIBLE_AGENT_ACTIVITY_TRACE_2026-09-05.md`,
`CHANGELOG/2026-09-05q`). No build yet.

## Finding

Independent of Orange's `tracing.py` work — that's a durable investigator
SQLite log; this is the live SSE activity stream already in the chat UI.
The tracing design explicitly lists a GUI viewer as a non-goal and
forbids `trace_id` on the route event without an `APP_REVISION` bump, so
the two tracks don't collide.

Real gaps identified in what's already on the wire but unused by the GUI:
`route.detail.capability`/`backend`/`reason`/`gpu_busy`, progress stages
(`review`/`decide`/`write`/`tool`/`evidence`), and `tool_evidence` (saved
on the assistant message and replayed to the model, but never shown to
the operator). Real gaps not on the wire at all: hop index, anything
during a farm Qwythos cold-load wait (silent for up to 45s per
2026-09-05o), and typed planning/`waiting_for_permission` states.

## v1 cut identified (no APP_REVISION bump)

GUI-only surfacing of existing SSE data: who-line, farm badge (fixing the
farm-turn-shown-as-CPU bug), pending-vs-error tool cards, restoring
`tool_evidence` visibility. This does not require new backend plumbing.

## Second cut (would bump APP_REVISION, not authorized here)

Hop-index field + emitting before the farm Qwythos wait starts. Real
backend change, deferred as its own PR — does not need to wait for
Orange's `traces.db`.

## Next

Operator authorization needed before v1 build starts (see chat).
