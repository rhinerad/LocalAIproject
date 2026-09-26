# 2026-09-24u — render_story_image: face_detail + realpro_flux fails fast; found (not fixed) a separate still-QA file-lookup regression

Operator reported a live batch failure: job 0 ("Wide interior view of a
modest apartment living room converted into a makeshift audition space...")
— `generate failed — batch item 0 — finished_without_manifest (pid 55888) —
ERROR: realpro_flux face_detail is not available until the isolated
custom-node startup is repaired`. The other 5 batch items (Scene Start
Images 2-5) never started (`stop_on_failure`, correct by design — see
`2026-09-23g`).

## Root cause

`work/image_render.py:736` has always hard-refused `face_detail=True` with
`model_profile=realpro_flux` (Flux) — this is a real, standing limitation,
not new. The chat agent chose that combination anyway: the `face_detail`
tool description ("Opt in to an automatic detected-face repair pass...")
never mentioned the Flux incompatibility, and this job's prompt describes a
person (an actor auditioning), so a face-repair pass was a reasonable-sounding
choice for a model that had no way to know it always fails with Flux — the
same tool-description-gap pattern as the earlier `reference_name`/mode
confusion (`2026-09-23`).

Worse than a wrong choice: `render_story_image` didn't validate the
combination until deep inside `image_render.py`'s own graph builder, which
only runs *after* `_start_owned_backend()` has already spawned a real
ComfyUI process and spent its startup time. So the mistake cost a full
backend-start cycle (pid 55888) before failing, and then blocked 5 unrelated,
valid Scene Start Image jobs behind it.

## Fix

`local_agent/tools.py`:
- `render_story_image()`: reject `face_detail=True` + `model_profile=realpro_flux`
  immediately after parsing args — before `router.gpu_busy()`, `gpu_gate.request()`,
  or `subprocess.Popen` are ever touched. `render_story_image_batch()` calls
  `render_story_image()` per job (confirmed by reading the loop), so this is
  covered for both the single-render and batch paths without a second change.
- Both `face_detail` tool-description strings (`render_story_image` and
  `render_story_image_batch`'s per-job schema) now say plainly: not available
  with `model_profile=realpro_flux`, use `realvisxl` if face repair is needed.

Backups: `local_agent/tools.py.bak_facedetailflux_20260924220404`,
`local_agent/test_render_story_image.py.bak_facedetailflux_20260924220506`.
Both files are LF; no line-ending changes.

## Tests

`test_render_story_image.py`: 2 new —
`test_refuses_face_detail_with_realpro_flux_before_spawning_backend` (asserts
`router.gpu_busy`, `gpu_gate.request`, and `subprocess.Popen` are never
called) and `test_face_detail_with_realvisxl_is_unaffected` (negative
control). Verified fail-then-pass: reverted `tools.py` to the pre-fix backup,
confirmed the new test fails for the right reason (execution reaches
`router.gpu_busy()`, which the test hadn't configured a return value for),
restored the fix, confirmed 24/24 pass.

`test_render_story_image.py` full file: 24 OK.

## Found, not fixed: `test_story_stills_batch_review.py` — 4 failing, unrelated to this change

While checking for regressions, `StoryStillQATests` (4 tests) failed with
`'fail' != 'not_run'` / `error: no rendered output file was found on disk to
check` — the still-QA wiring from `2026-09-24a` cannot find the rendered PNG
its own test fixture lays down. **Confirmed unrelated to this entry**: reverted
`tools.py` to the pre-face_detail-fix backup and reran — identical 4 failures,
byte-for-byte same output. So this regressed sometime between `2026-09-24a`
(when this test suite was presumably passing) and now, most likely from one
of the same-day sessions that also touched `tools.py`'s output-path handling
(`24e` truncated-prompt guard, `24f` batch-failure cards, `24g` chat-video
watch, `24p` card wording) without rerunning this specific suite.

This matters beyond test hygiene: if the QA lookup is broken the same way in
production, the still-QA safety net wired in this morning could currently be
silently returning `not_run` instead of a real verdict on real renders — the
opposite of fail-closed. **Did not investigate further or fix** — multiple
sessions are actively editing `tools.py` today (see `24t`'s note on leaving
another session's in-progress files alone), and this needs someone who can
diff the manifest/output-path handling across today's `tools.py` changes
without racing a concurrent edit. Failing tests:
`test_batch_carries_qa_into_completed_review_payload_and_summary`,
`test_completed_status_runs_creative_approve_with_manifest_prompt`,
`test_qa_crash_is_reported_as_error_never_as_pass`,
`test_regression_operator_empty_room_fails_real_qa_and_reaches_review`.

## Operator

The failed batch is dead — job 0 never produced a manifest, so nothing to
resume. Resubmit the 6 Scene Start Images without `face_detail` (or with
`model_profile=realvisxl` if a face-repair pass is wanted). Before that batch
is trusted, the `StoryStillQATests` regression above should be resolved first
— it directly affects whether the still QA those renders now go through
actually runs.
