# 2026-09-24w — image_render: tolerate transient /history poll failures

## Problem

`work/image_render.py` `_wait_for_outputs` polled `/history/<prompt_id>` via
`_get_json` (8 s timeout). `_get_json` wraps URLError/OSError/timeouts in
`ImageRenderError`, and the loop's `except ImageRenderError: raise` re-raised it
at once, so the `except Exception: pass` meant for transient polling failures
never saw transport errors. One slow `/history` response killed the job.

Evidence: `work/runtime/agent_image_jobs/startup-deadline-fix-verify_run2_20260924_185909.log`
exited 2 with `ComfyUI API unavailable at .../history/09a1f706-...: timed out`,
while ComfyUI (`work/runtime/image_render_runtime/logs/comfy_20260924_185910_757374.stderr.log`)
logged `Prompt executed in 00:12:16` and wrote
`outputs/stories/_comfy_output/stories/startup-deadline-fix-verify/renders/bfa0d801c89941669f1a1586a6195c7b_00001_.png`
at 19:14:32. No manifest was written; that PNG is orphaned and was left untouched.

## Change

- The `_get_json` call now has its own `try`: an `ImageRenderError` from it is
  recorded and printed (`history poll failed, retrying: ...`), followed by the
  existing 2 s sleep, and polling continues within `timeout_s`. The final
  timeout message appends the last poll error.
- Unchanged and still immediate: the owned-process-exited check, the
  `status_str == "error"` graph-failure raise, and the
  `thermal_guard.check_running_ceiling` call and its 15 s cadence.

## Tests

Added to `local_agent/test_production_integrity.py` `IntegrityTests`:
`test_wait_for_outputs_tolerates_history_timeout` (one "timed out" then outputs
→ images returned), `test_wait_for_outputs_graph_error_still_raises`,
`test_wait_for_outputs_backend_exit_still_raises`.
`python -m unittest test_production_integrity` from `local_agent/`: 51 tests OK.

## Verification status

Live run 19:21–19:35 local, story `history-poll-fix-verify`, same args as the
failed verify run except seed 2
(`work/runtime/agent_image_jobs/history-poll-fix-verify_20260924_192136.log`):
exit 0, `Prompt executed in 00:11:41`, manifest
`outputs/stories/history-poll-fix-verify/manifests/image_2d2834d6-6dec-437a-8460-82c9c70d6f2f.json`
status `complete`, PNG exists (1,346,575 bytes) and its sha256 matches the
manifest. Backend stopped, owner released, port 8188 free afterwards.

**The retry path itself was not exercised live**: the log has no
`history poll failed` line, so no `/history` poll timed out this time. That path
is covered only by the unit test. The run confirms the normal completion path
still works after the change. The orphaned verify-run PNG from run 2 has not
been adopted into a manifest at the time of this entry; it was adopted later in `2026-09-24z`.
