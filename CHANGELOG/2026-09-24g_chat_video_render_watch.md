# 2026-09-24g — render watch extended to chat video batches (`start_current_chat_render`)

## Why

`2026-09-24b` added `/api/render_watch` so a still (`render_story_image`) or a
`comfy_generate` job that lands after the agent's reply ends is announced and
saved onto the reply. Video batches started from a chat ("start render") were
not covered, and they are the renders most likely to finish long after the
turn ends.

## How a chat render job is identified and observed (read-only)

Established from `local_agent/chat_render_jobs.py`, `tools.start_batch_render`
and `work/batch_render_folder.py`. No runner code changed.

- **Identity:** `start_current_chat_render` returns
  `{"prepared": {...}, "launch": {"started", "pid", "job_folder", "planned_renders", "limit", "log"}}`.
  `job_folder` is `local_agent/render_jobs/<cid>/render_<stamp>[_NN]/`; `pid`
  is the runner process. The watch id is `chat_render:<pid>:<cid>/<job>`.
- **Progress / outputs:** the runner writes `<job>/batch_manifest.json`
  (`renders[<key>].status` = `done` / `failed` / `invalid` / `error`, with
  `output_path` for `done`) and moves each finished take to
  `<job>/renders/<key>[_attemptN].mp4`.
- **Completion:** the runner logs `Batch complete: N/M renders done` as its
  last line, *after* releasing `batch_render_queue_owner.json`. A crash
  (for example `RuntimeError: ComfyUI exited during startup rc=1`, seen in the
  real job `5b3352e81fdb4f08/render_20260824_184105`) leaves only a traceback
  in `<job>/batch_runtime/logs/agent_batch_*.log`.
- The watch treats the job as finished when the log shows the marker or the
  PID is no longer live (`tools._pid_is_live`, the same tasklist check the
  launch preflight uses). It reads the manifest and log only. It does not touch
  the queue lock, the ports, ComfyUI or the runner.

## Changes

`local_agent/server.py`
- New media root id **`chat_render`** → `CHAT_RENDER_JOBS_ROOT`
  (`local_agent/render_jobs`). It serves **video only**, and only files at
  exactly `<cid>/<job>/renders/<file>`. The job folder also holds copies of the
  chat's uploads (`img0/`, `img1/`, `video_refs/`) and the Comfy scratch
  (`batch_runtime/`). None of those are servable. `forbidden_media_roots()` is
  unchanged: `outputs/equal_shares`, chats, uploads and Shared input are still
  refused for every root.
- `media_kinds_for_root()` replaces the duplicated
  `"media" if shared_output else "image"` choice in `generated_media_payload`
  and `reveal_generated_media`.
- `chat_render_job_dir()` and `collect_chat_render_media_artifacts(job, manifest)`
  turn `done` manifest entries into ready video locators through
  `resolve_generated_media` + `media_artifact_for`.
- `register_render_watch` accepts `start_current_chat_render` (nested `launch`)
  and a bare `start_batch_render`, but only when `job_folder` is a chat job
  folder. An operator-supplied folder elsewhere is not watched, because its
  files could not be served.
- New watch kind `chat_render`:
  - Still running → keep waiting.
  - At least one video, all planned renders done → `complete`.
  - Some videos plus failed/invalid entries, or fewer than `min(planned, limit)`
    → `complete` with the videos plus one summary error card
    (`card_key chat_render_partial|<id>`), e.g.
    `1 of 3 renders done; 0002 failed: …`.
  - No videos → `failed`, with the manifest error or the log's last line.
- Expiry for this kind is 72 h, because each attempt may run 120 min. It only
  ends a watch whose PID Windows reused. Failure cards for this kind are
  `kind: video`.

`local_agent/agent.py`
- `MEDIA_SOURCE_TOOLS` += `start_current_chat_render`, `start_batch_render`.
  Their result carries `prepared.provenance`, which can push `launch` past the
  4000-char clip.
- The deterministic "start render" path (`_explicit_folderless_render_request`)
  now calls `_emit_tool_result(...)` instead of `emit("tool_result", result[:4000])`,
  so it registers the watch the same way a native tool call does.

`static/index.html` is unchanged. `mountMediaArtifact` already renders
`<video controls>` and passes `art.root` through to `/api/generated_media`.

Backups: `server.py`, `agent.py`, `test_render_media_announce.py` →
`*.bak_chat_render_watch_20260924_013032`. (Another session edited
`server.py` / `test_render_media_announce.py` concurrently. The edits were
kept to separate regions, and the new tests are a new class appended at the
end.)

## Evidence

- `python -m unittest test_render_media_announce test_chat_render_jobs` →
  **33 tests OK**. The new `ChatRenderWatchTests` class has 9 tests: servable
  paths and refusals; native registration through `_TurnHarness` with a
  result longer than 4000 chars; the folderless path through the real
  `agent.answer` with "start render"; running → complete, attached once and
  servable by sha; log marker despite a live (reused) PID; crash → video
  failure card with the traceback line; partial batch summary card; `limit`
  lowering the expected count; foreign / nested / ERROR / prepare-only results
  not watched.
- Mutation check: with the two tools removed from `MEDIA_SOURCE_TOOLS`, 8 of
  the 9 new tests fail. The one that still passes is the servability test,
  which does not depend on registration.
- Neighbouring suites `test_action_resolver test_comfy_tools
  test_native_tool_calling test_render_story_image test_story_image_reveal
  test_story_stills_batch_review` → **265 tests OK**.
- **Not verified live:** no batch render was started for this change, per the
  observe-only rule. The first real chat render will be the end-to-end check:
  the toast, and the card on the reply after reload.

## Known limits

- *(Fixed in `2026-09-24p`.)* The summary error card reuses the GUI's generic error rendering
  ("generate failed — <note>"), so a partial batch reads as
  "generate failed — 1 of 3 renders done; …".
- A batch launched with `start_batch_render` on a folder outside
  `local_agent/render_jobs/` is still not announced, by design.
