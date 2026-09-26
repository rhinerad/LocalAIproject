# 2026-09-06l — GUI Send stuck on Stop (busy never clears)

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06l**.

## Symptom

Operator: turn got stuck because the **send button never came back**; the
**stop button just kept showing**. Related Flux chats (`5404c50e34aa4e53` /
`5c5b5b96f0e44966`) showed `waiting_for_permission`, `_ [stopped]_`, tool
errors, and empty completions — UI should still restore Send on every
terminal path.

## Root cause

`local_agent/static/index.html` `stream()`:

1. Set `busy=true` and relabeled Send → Stop with **no `try/finally`**.
   Any thrown error while parsing/handling an SSE event (`JSON.parse`,
   DOM update, etc.) exited the function and left Stop stuck forever.
2. Stop only `POST /api/stop` and `return`ed — it did **not** clear
   `busy`. If the server was blocked inside a tool/Ollama call that does
   not poll `should_stop`, the SSE reader never ended and Send never
   returned.

GPU `waiting_for_permission` itself is non-blocking (gate parks a sidebar
card and the turn continues on CPU). It was not a server wait-loop; the
client busy flag was the hang.

## Fix

`local_agent/static/index.html`:

- `streamEpoch` + `setBusy()` helper.
- `stream()` wraps the fetch/reader in `try/catch/finally`; the owning
  epoch always restores Send when the stream ends (done, error, empty
  body, exception, disconnect).
- Per-event `JSON.parse` / handler try/catch so one bad event cannot
  stick the button.
- Stop click bumps `streamEpoch` and calls `setBusy(false)` **immediately**,
  then POSTs `/api/stop`. The orphaned reader keeps draining (no abort) so
  the server can persist `_ [stopped]_` without BrokenPipe.
- `waiting_for_permission` still refreshes the sidebar; busy clears when
  the stream ends or the operator hits Stop (turn is not a parked SSE).

## Ship

- `APP_REVISION` / `$ExpectedAgentRevision` →
  `2026-09-06-send-stop-unlock-r91` (for the **next** restart; this change
  did **not** restart the live agent).
- Regression: `local_agent/test_gui_render_hint.py` asserts the unlock
  markers (`streamEpoch`, `setBusy`, `finally`, Stop bumps epoch).

## Manual UI path (until restart loads r91)

1. Hard-refresh the GUI after restart so `index.html` is not cached.
2. Send a turn; confirm Send → Stop while streaming.
3. Click Stop mid-turn: Send must return immediately; chat may later show
   `_ [stopped]_` after the server observes the stop set.
4. Force a bad path (tool error / empty completion / permission note):
   after the stream ends, Send must be visible again.
5. Confirm a new message can be typed and sent without reloading.

## Verification

- Unit: `python -m unittest local_agent.test_gui_render_hint local_agent.test_launcher_revision -v`
- Did **not** run `START_LOCAL_AGENT_GUI.ps1`; did **not** kill `server.py`.