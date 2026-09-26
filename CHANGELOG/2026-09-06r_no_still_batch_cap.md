# 2026-09-06r — Remove artificial still-batch size cap

Date: 2026-09-06 (evening ET). Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06r**
(p/q already claimed elsewhere; this entry uses the allocated **r**).

## Operator goal

Full CLIP start/end still sheets (dozens to ~250 unique frames for a long
clip pass) must queue in **one** `render_story_image_batch` call. Rhine saw
the agent claim a batch was "capped at 24 stills due to the system's limit"
— that was a product hard cap, not a real system limit. Remove it.

## Changes

### A. No product still-batch cap

- Removed `_MAX_BATCH_JOBS = 24` and the `ToolError` that rejected
  `len(jobs) > 24` in `render_story_image_batch`.
- Prefer no ceiling (accidental million-item JSON is still bounded by normal
  request parsing / practical queue time).

### B. Guidance

- `plan_story_image` next_step + tool text, `render_story_image_batch` tool
  text / docstring / schema: queue **ALL** unique start/end frames in one
  batch; no artificial batch size limit; never tell the operator a batch was
  capped.

### C. Revision

- `APP_REVISION=2026-09-06-no-still-batch-cap-r94` in `local_agent/server.py`
- `$ExpectedAgentRevision` synced in `START_LOCAL_AGENT_GUI.ps1`

## Tests

- New: `test_batch_accepts_more_than_former_24_job_cap` (30 mocked jobs all
  run; would have failed under old cap).
- `python -m unittest test_story_stills_batch_review test_launcher_revision -v`

## Live

Did **not** restart the live agent. Process still on r93 until Rhine restarts
(e.g. `local_agent\START_LOCAL_AGENT_GUI.ps1`). Do not kill PID 33244 without
an intentional restart. After restart, `/api/status` should show
`2026-09-06-no-still-batch-cap-r94`.
