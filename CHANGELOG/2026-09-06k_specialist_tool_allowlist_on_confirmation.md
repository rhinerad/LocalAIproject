# 2026-09-06k — Stale specialist-tool block on "proceed" after image plan

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06k**.

Live bug on chat `5404c50e34aa4e53`: turn 1 ran `plan_story_image`
(`model_profile=realpro_flux`, story `vhs_liminal_space_story`) successfully.
Operator replied `proceed`. Turn 2 called `render_story_image` and got
`ERROR: stale specialist-project tool selection blocked. The current operator
message did not ask for this project scope, so the tool was not run.` No PNG
was written.

## Root cause

`specialist_scope` (used by the tool allowlist at `run_one`) was computed only
from `_requests_specialist_project_context(latest_user)`. A bare confirmation
like `proceed` / `yes` / `go ahead` never matches that regex, so every tool in
`_SPECIALIST_PROJECT_TOOLS` (including `render_story_image`,
`plan_story_image`, `story_image_job_status`) was refused.

`2026-09-06f` already fixed the **reply-text** sibling of this guard by adding
`_pending_specialist_continuation(history)` for `_irrelevant_specialist_reply`.
The **tool-selection** path never consulted that helper.

The live prior assistant turn also said "I will proceed to generate" (assertive)
rather than an explicit "would you like" offer, and persisted successful
`plan_story_image` in `tool_evidence` — both are active undeclined invitations
to continue.

## Fix

`local_agent/agent.py`:

1. `specialist_scope = request(latest_user) or _pending_specialist_continuation(history)`.
2. Broadened `_SPECIALIST_CONTINUATION_OFFER_RE` for prepared-plan / "I will
   proceed to generate" / `plan_story_image` / `call render_story_image` prose.
3. New `_assistant_planned_story_image`: successful `plan_story_image` in the
   immediately prior assistant `tool_evidence` / `activity` counts as pending
   continuation (covers the live chat shape even if prose is terse).

Deliberately still requires an *active* prior invitation — declined prior
turns ("No render was started...") stay out of scope, so
`test_stale_h3_render_tool_is_blocked_on_unrelated_turn` remains green.

## Tests

```
python -m unittest local_agent.test_native_tool_calling -v
```

101/101, including new
`test_confirmation_proceed_after_image_plan_allows_render_story_image` and
existing stale-H3 reply/tool regressions.

## Files

- `local_agent/agent.py`
- `local_agent/test_native_tool_calling.py`
- `local_agent/server.py` (`APP_REVISION`)
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `CHANGELOG/2026-09-06k_specialist_tool_allowlist_on_confirmation.md`
- `GROK_STATUS.md`
- `TODO.md`

## Revision

`APP_REVISION=2026-09-06-specialist-tool-confirm-r90`


## Live verification (DuranGamingPC)

1. Restarted `local_agent/server.py`; `/api/status` reports
   `APP_REVISION=2026-09-06-specialist-tool-confirm-r90`. `:8188` closed; GPU idle.
2. `/api/regenerate` on chat `5404c50e34aa4e53` (last user text `proceed`):
   `render_story_image` **was invoked** (no longer
   `stale specialist-project tool selection blocked`). Model omitted `prompt`
   on regenerate → `ERROR: prompt is required` — guard fix confirmed; args
   still model-dependent on that path.
3. `/api/action` `render_story_image` smoke (`model_profile=realpro_flux`,
   story `vhs_liminal_space_story`, clip1-start prompt) returned
   `ERROR: GPU permission pending in the sidebar; approve the image render once, then retry`.
   Pending gate id: **`gpu_a38b751666c5`**
   (`workload=ComfyUI still-image render`, `key=image_render:vhs_liminal_space_story`).
   Also pending unrelated chat load: `gpu_37d6fee2add9`.
   Waiting on operator sidebar approval — not auto-approved.
