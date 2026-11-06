# 2026-09-06n — Continue / finish-earlier unlocks story-image tools after plan

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06n**.

Live bug on chat `d98731129ac743ac`: turn 1 ran many successful
`plan_story_image` calls (Flux photo+video START/END frames). Operator said
`continue` → every `plan_story_image` hit
`ERROR: stale specialist-project tool selection blocked...` and the assistant
replied that the tool was "outside the current request". Operator then said
`the first prompt i sent still needs to finished.` → same block on
`render_story_image`.

## Root cause (why r90 / 2026-09-06k missed this)

r90 set `specialist_scope = request(latest) or _pending_specialist_continuation(history)`
and taught `_assistant_planned_story_image` to read `tool_evidence` on the
**immediately prior assistant message**. Unit tests passed because they put
`tool_evidence` directly on that assistant dict.

The live desktop path in `server.py` did **not** forward `tool_evidence` on
the history rows passed to `agent.answer()`. It only copied `role`/`content`
and appended a separate system receipt:

`Saved local tool evidence from this same conversation...`

So `_assistant_planned_story_image(last_assistant)` was always False on the
live path. The prior assistant prose in this chat ("successfully planned" /
"created a set of inspectable ... graphs") also did not match
`_SPECIALIST_CONTINUATION_OFFER_RE`, so `_pending_specialist_continuation`
returned False for bare `continue`.

After the blocked reply, the immediately-previous assistant was the refusal
itself (error outcomes only), so a second finish-up utterance still failed
even if evidence had been attached to the original plan turn.

## Fix

1. `local_agent/server.py` — attach a compact `tool_evidence` list on
   assistant history rows (keep the system receipt for the model).
2. `local_agent/agent.py`:
   - Broaden offer prose (`successfully planned`, inspectable graphs).
   - Parse the server's system evidence receipts as plan/render evidence.
   - History-aware unfinished plan: successful `plan_story_image` without a
     later successful `render_story_image`.
   - Continuation utterances (`continue`, `keep going`, `finish it`,
     `still needs to be finished`, `first prompt` / `earlier` finish-ups)
     reopen specialist scope when unfinished image work exists in **this**
     chat; phrases that name another project (`powerinfer`, `calibration`,
     ...) stay out of scope so stale-H3 regressions remain green.

## Tests

```
python -m unittest local_agent.test_native_tool_calling
```

103/103, including:

- `test_continue_after_image_plan_via_system_evidence_allows_render`
- `test_finish_earlier_prompt_after_blocked_reply_allows_render`
- existing `test_confirmation_proceed_after_image_plan_allows_render_story_image`
- existing stale-H3 reply/tool regressions

## Files

- `local_agent/agent.py`
- `local_agent/server.py` (`APP_REVISION`)
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_native_tool_calling.py`
- `CHANGELOG/2026-09-06n_specialist_continue_finish_earlier_prompt.md`
- `GROK_STATUS.md`
- `TODO.md`

## Revision

`APP_REVISION=2026-09-06-specialist-continue-finish-r92`

**Did not restart** `server.py` / `START_LOCAL_AGENT_GUI.ps1` (operator
constraint). Live process still needs a later restart to pick up r92.
