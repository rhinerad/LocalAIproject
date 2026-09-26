# 2026-09-24b — local_agent GUI: review stills/video inline, announce renders that land after the reply

## Why

Operator asked for (1) generated stills/video to appear in the chat for human
review instead of being hunted down in Explorer, and (2) the GUI to announce
finished generations even after the agent's turn has ended.

The GUI already had a complete inline-media card system (`mountMediaArtifact`,
`/api/generated_media`, `media_artifacts` on stored replies). Measured on the
84 stored chats: 38 assistant turns called story-image tools
(`render_story_image` 25, `story_image_job_status` 7, `render_story_image_batch` 6)
and **zero** media artifacts had ever been stored.

## Root causes (three, not one)

1. `server.collect_story_media_artifacts()` only understood the single-job
   result shape. `render_story_image_batch` returns an aggregate
   (`{"batch": true, "completed": [...], "failures": [...], "pending": [...]}`)
   with no top-level state/status → it returned `[]` for every batch.
2. `agent.py` clips every emitted `tool_result` to `result[:4000]` before
   `server.push` sees it. One real realpro_flux manifest is ~4.4 KB on disk, so
   batch results *and* single-job `story_image_job_status` results
   (manifest + up to 3 KB log tail) arrived as truncated JSON → `json.loads`
   failed → `[]` regardless of shape.
3. Found in the live run: live cards were mounted inside the tool-result
   lifecycle card, a collapsed `<details>`, so the stills were hidden until the
   operator expanded it (history reload mounted them visibly in the bubble).

Also fixed, because (2) would otherwise have exposed it:
`tools.story_image_job_status` reported the story's *newest manifest on disk*
even when it predated the job being polled. Re-rendering an existing story
would have shown the previous still inline as though it were the new result.

## Changes

- `local_agent/agent.py`: `MEDIA_SOURCE_EVENT = "tool_media_source"`,
  `MEDIA_SOURCE_TOOLS`, `_emit_tool_result()`. Visible `tool_result` is
  unchanged (still clipped at 4000); for media tools (non-ERROR results) one
  extra internal event carries the full result. Used in `_execute_plan` and the
  native tool loop. The phone bridge ignores unknown event kinds.
- `local_agent/server.py`:
  - batch-aware `collect_story_media_artifacts()` → per-job `_story_job_artifacts()`;
    failures/not-started entries yield nothing (follow-up task filed).
  - `media_artifact_key()` / `extend_unique_artifacts()`: one card per file per turn.
  - `push()` consumes `tool_media_source` (never forwarded to the browser,
    not recorded by `learning`, not in the activity trace).
  - Render-watch registry: `runtime/render_watch.json`, `register_render_watch`
    (render_story_image pid/story/log; comfy_generate prompt_id),
    `poll_render_watches` (5 s check TTL, 2 h expiry, 24 h retention),
    `_attach_late_artifacts` (saves late cards onto the chat's latest
    assistant reply, skipping files the turn already showed; failures become an
    error card). Watches for a chat are not resolved while that chat has an
    active turn (`_active_turns`). New `GET /api/render_watch`.
  - `media_queue` deliberately not reused: it is a work queue the media
    watcher claims; a render parked there would sit pending forever and
    "Clear queue" would cancel it without stopping anything.
- `local_agent/tools.py`: `_story_job_started_at()` parses the launch time from
  render_story_image's `<story>_<YYYYmmdd_HHMMSS>.log`; `story_image_job_status`
  then only considers manifests written after launch (earliest wins). Unparsable
  log names keep the old behaviour. (2026-09-24a's still QA now runs on this
  job-scoped manifest.)
- `local_agent/static/index.html`: live cards mount in the reply bubble;
  `mediaKey` de-dup; "Finished after the reply" label and error note on cards;
  `pollRenderWatch()` every 10 s + 1.5 s after each turn; toast (click opens the
  chat and scrolls to the card) and `(n) ● Local Agent` title unread count when
  the window is unfocused/hidden; a turn that delivered media while the operator
  was away also toasts. No Notification API / sound (operator: not wanted).

Backups: `*.bak_inlinemedia_20260924T002509` for agent.py, server.py, tools.py,
static/index.html, test_story_image_reveal.py, test_render_story_image.py.

## Tests

New `local_agent/test_render_media_announce.py` (batch shape with 2 completed /
1 failed / 1 not started; truncation regression; dedupe; `_emit_tool_result`;
full `_send_turn` SSE path; render-watch register/resolve/dedupe/failure/
active-turn/comfy/prune). New
`test_render_story_image.test_manifest_from_before_this_job_launched_is_not_reported_complete`.
After merging with 2026-09-24a's concurrent agent.py/tools.py edits:
`test_render_media_announce test_story_stills_batch_review test_render_story_image
test_story_image_reveal test_native_tool_calling test_auto_farm_routing
test_activity_trace test_gui_render_hint` → 244 OK.
Full non-live suite: 16 failures/errors, all in files this entry does not touch
(stale APP_REVISION pins, remote allowlist, tracing, dspy/GVD/watchdog); tracked
as a separate task.

## Live verification (real GUI, real GPU renders, server restarted 00:52)

- 2-still RealVisXL batch via chat: two image cards streamed mid-turn; after
  reload both render visibly in the reply with working "Open containing folder".
- Late render: one real `render_story_image` job registered as a watch for
  that chat after its reply ended; `/api/render_watch` went running → complete
  with the **new** still (story already held two earlier manifests, confirming
  the job-scoping fix live). GUI mounted it labelled "Finished after the reply",
  showed the toast, and set the title to `(1) ● Local Agent`; clicking the
  toast cleared it; the artifact was persisted on the reply.
- Caveat: the SSE → `register_render_watch` hop was exercised by unit tests,
  not live. The 14B model twice answered "The render has started." without
  calling any tool, so the live job was launched in a separate process and
  registered through the same function.

Test leftovers (chat `bd7d15f89d3748a4`, three `inline_card_test` stills and
manifests): chat moved to `local_agent/chats/_deleted/` by `store.delete`; stills
and manifests moved to `outputs/stories/_QUARANTINE_inline_card_test_2026-09-24/`
(permanent deletion was denied by the permission layer). Job logs under
`work/runtime/agent_image_jobs/inline_card_test_*` and the chat's
`work/runtime/story_stills_review/bd7d15f89d3748a4.json` were left in place.

## Follow-ups filed

- Inline error cards for failed / not-started batch jobs.
- Watch `start_current_chat_render` video renders for late completion.
