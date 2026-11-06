# 2026-09-24ab — still QA reported `not_run` for every still under a POSIX pathlib: ComfyUI backslash subfolders; resolver now splits on both separators

## Why

`2026-09-24u` ("Found, not fixed") reported four `StoryStillQATests` failing with
`'fail' != 'not_run'` and `error: no rendered output file was found on disk to
check`, confirmed by revert-and-rerun to be unrelated to the face_detail fix, and
attributed it to a same-day edit of `local_agent/tools.py`'s output-path handling.
This session's brief: find the root cause, make `error` / `fail` / `not_run`
three distinct states, prove it fail-then-pass.

## What was actually wrong (differs from the brief)

- **Not a regression from any same-day `tools.py` edit.** `_resolve_story_still_outputs`
  is byte-identical in every backup since `2026-09-24a` landed it
  (`tools.py.bak_promptprefix_20260924T012949` 01:07, the three
  `bak_facedetailflux_*` copies, `bak_qaanchor_20260924` 21:26, and current: same
  md5 of the function body). The four tests' fixtures are also unchanged since
  `24a`; `24aa`'s test-file diff is additive only.
- **On this host the tests pass.** First thing checked: current code, Windows
  Python 3.12.10, `python -m unittest test_story_stills_batch_review.StoryStillQATests`
  → 13 OK, including all four named tests.
- **Reproduced under a POSIX Python.** WSL Ubuntu-24.04, Python 3.12.3, same
  tree via `/mnt/a/...`: FAILED (failures=7, skipped=2). The seven are the four
  from `24u` minus `test_regression_operator_empty_room_fails_real_qa_and_reaches_review`
  (skipped there: no cv2 in WSL), plus three of `24aa`'s new anchor tests. Every
  failing test locates the still through the manifest; every passing one hands
  `_story_still_qa` a path directly. All seven report `verdict=not_run`.
- **Mechanism.** ComfyUI on Windows reports `subfolder` as `stories\<story>\renders`
  and `work/image_render.py` stores it verbatim — every real manifest under
  `outputs/stories/` has it (e.g. `Scene-Start-Image-1/manifests/image_fb498057-….json`:
  `"subfolder": "stories\\Scene-Start-Image-1\\renders"`). The test fixture writes
  the same shape. `_resolve_story_still_outputs` did `comfy_root / subfolder / filename`;
  pathlib splits only on the *running* interpreter's separator, so under a POSIX
  pathlib the backslashes are literal filename characters, `is_file()` is False,
  `path` is `None`, `_story_still_qa` has nothing to check and returns `not_run`
  with "no rendered output file was found on disk to check" — for a file that
  exists exactly where the manifest says. The `24u` session evidently ran the
  suite under a POSIX Python that also had cv2 (its real-QA test failed rather
  than skipped). The `/history` output parser at `tools.py:1153` already
  normalises `\` → `/` for the same reason; the still resolver did not.
- **The three verdict states were already distinct in the verdict logic:**
  `error` = `creative_still_qa` failed to import or `creative_approve` raised;
  `fail` = the checker ran and rejected; `not_run` = no file or no prompt to
  check. Nothing mapped an `error`/`fail` to `not_run`; the file lookup failed
  before QA could run. The consequence `24u` feared was real for that platform:
  every still would read `not_run` instead of a verdict. Production on this
  Windows host was never affected — the real `pass`/`fail` records under
  `outputs/stories/*/still_qa/` (`24a`, `24aa`) show the lookup working here.

## Changes — `local_agent/tools.py` (backup `tools.py.bak_qaposixpath_20260924`)

- New `_split_comfy_subpath(value)`: splits a ComfyUI-reported subfolder or
  filename on both `\` and `/`, dropping empty and `.` segments.
  `_resolve_story_still_outputs` now builds the path with
  `comfy_root.joinpath(*segments)` instead of `comfy_root / subfolder / filename`.
  The manifest's `subfolder` string is still recorded verbatim in each entry;
  `expected_path` is the normalised location.
- `_story_still_qa` `not_run` diagnostics: a manifest with no outputs →
  `"the render manifest lists no output file to check"`; outputs listed but none
  on disk → `"no rendered output file was found on disk to check (looked for:
  <expected_path>; …)"`, so a mis-resolved or missing path is visible to the
  operator instead of reading like a QA verdict. Verdict semantics unchanged.
- Not touched: verdict/caching logic, the `24aa` anchor registry, `24u`'s
  face_detail / model_profile validation, `creative_still_qa.py`, `image_render.py`.

## Tests — `local_agent/test_story_stills_batch_review.py` (backup `.bak_qaposixpath_20260924`)

- `test_missing_output_file_is_not_run_not_pass` additionally asserts the record
  names the path it looked for.
- New `test_manifest_without_outputs_is_not_run_with_distinct_reason`.
- New `test_resolver_finds_still_from_windows_or_posix_subfolder`: backslash,
  forward-slash and mixed/trailing subfolders all resolve to the fixture PNG
  (fails on a POSIX host without the fix).
- New `test_resolver_under_posix_pathlib_splits_windows_subfolder`: patches
  `tools.ROOT` with a `PurePosixPath` subclass whose `is_file()` answers from a
  set, so the POSIX join is modelled on any host; also checks a genuinely
  missing still's `not_run` record names the expected POSIX path. Fails on
  Windows without the fix.

### Evidence — fail, then pass, on both interpreters

| step | Windows py3.12.10 | WSL Ubuntu-24.04 py3.12.3 |
|---|---|---|
| original `tools.py`, original tests | 13 OK | FAILED (failures=7, skipped=2) |
| original `tools.py`, new tests (revert check) | FAILED (failures=3) | FAILED (failures=11, skipped=2) |
| fixed `tools.py`, new tests | 16 OK | 16 OK (skipped=2: cv2/models absent in WSL) |

WSL failures with the original code: `test_batch_carries_qa_into_completed_review_payload_and_summary`,
`test_batch_passes_story_anchor_to_creative_approve_after_prior_approval`,
`test_completed_status_runs_creative_approve_with_manifest_prompt`,
`test_corrupt_or_stale_anchor_registry_degrades_to_no_anchor`,
`test_first_still_for_story_runs_qa_with_anchor_none_without_error`,
`test_per_image_story_labels_fall_back_to_last_still_approved_in_chat`,
`test_qa_crash_is_reported_as_error_never_as_pass` (`'error' != 'not_run'`),
plus with the new tests the two resolver tests, `test_missing_output_file_is_not_run_not_pass`
and `test_manifest_without_outputs_is_not_run_with_distinct_reason`.
Windows revert-check failures: the three tests that assert the new behaviour
(`test_manifest_without_outputs_…`, `test_missing_output_file_…`,
`test_resolver_under_posix_pathlib_…`). The fixed `tools.py` md5
(`c7d63ff7b2c6c5a5153e5d116f395b31`) was identical before the revert and after
the restore.

Full `local_agent` suite (Windows), `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
Ran 1526 tests in 327 s → OK (skipped=2), exit 0, 351 s wall clock, with the fixed
`tools.py` and the new tests in place (2026-09-24 22:23–22:29 local).

## Housekeeping

- `scripts/next_changelog_id.py` was called twice this session; it claims each
  id it prints. Removed this session's own stray claim
  `CHANGELOG/.id_claims/2026-09-24ac` (pid 40536, created 22:19 by the second
  call) so the letter is not burned. This entry is `ab`.

## Not done / follow-ups

- `work/image_render.py:1655` joins `IMAGE_OUTPUT / subfolder / filename` the
  same way; it runs on the ComfyUI host, so separators always match there. Left
  alone.
- Per `24aa`, the running GUI `server.py` (pid 11684) had `24a` code loaded; if
  it has not been restarted since, it has neither `24aa` nor this change.
- `24u`'s operator note said the `StoryStillQATests` regression should be
  resolved before the next Scene Start batch is trusted: resolved. On this
  Windows host the QA lookup was never affected; it is now platform-independent.
