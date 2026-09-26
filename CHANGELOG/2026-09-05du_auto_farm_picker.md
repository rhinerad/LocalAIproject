# 2026-09-05du — GUI “Auto (may use Mac farm)” unpinned mode

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05du**.

Builds the Later PR from
`CHANGELOG/2026-09-05dg_farm_gui_expose_scope.md`. Gates were
`2026-09-05dl` (Qwythos `read_artifact` loop) and `2026-09-05ds`
(pre-wait proposal farm route). Does not change `decide()` farm_status
fail-open, farm_skip timeshare, or `prefer=cpu`. Does not unpin any
existing Huihui/Coder chat. No 5080-busy veto.

## What shipped

Picker option **`auto_farm`**: “Auto (may use Mac farm) — unpinned;
tool turns may use Qwythos”. Distinct from a pinned model tag and from
today’s pin path (invalid/empty model → `router.decide(prefer)` **then
store that tag**). The farm option is **not** the default; refresh still
selects the first available local model unless the open chat is already
`routing=auto_farm`.

New chats in this mode: `store.create(..., model="", routing="auto_farm")`.
`_send_turn` / `/api/new` skip `_valid_chat_model` and the
`decide()`-then-pin path. `agent.answer(..., model=None)` via
`answer_model_for_conversation`. Legacy chats with empty `model` and
**no** `routing=auto_farm` still get the one-time pin migration.

`POST /api/send` conversation SSE includes `routing`. Who-line still
only updates on observation `route` (ds).

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-auto-farm-r83`.

## Tests

```
python -m unittest test_auto_farm_routing test_launcher_revision -v
```

11/11 in that pair (plus launcher). Covers:

1. `_send_turn` with `model=auto_farm` stores empty model +
   `routing=auto_farm` and `agent.answer` receives `model=None`.
2. Pinned Huihui-14B: `decide` would return farm if `model is None`,
   but `try_qwythos_on_farm` is never called.
3. Auto-farm conv + real `agent.answer` farm mock: `on_event` sees
   “Waiting on Mac Qwythos” + proposal farm `route` **before** the
   mocked wait, then observation farm `route` (ds sequence) through
   `answer_model_for_conversation` — the same kwarg `_send_turn` uses.
4. Empty-model-without-routing is still migrated/pinned, not farm.

Plain pin path (`decide().model` then store) unchanged.

## Files

- `local_agent/server.py`
- `local_agent/store.py`
- `local_agent/static/index.html`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_auto_farm_routing.py`
- `TODO.md`
