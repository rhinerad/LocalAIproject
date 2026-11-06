# 2026-11-06a — Audit remediation, part 1: hygiene, docs, and the first pass of code fixes

Evidence: `AUDIT_2026-11-02.md` (the audit), commits "Repo hygiene and docs
consolidation from the 2026-11 audit" and "WIP: audit code fixes from five
parallel agents" on `claude/epic-hypatia-6mrayy`; test runs below. Handoff
for the remaining work: `docs/HANDOFF_PROMPT_2026-11-06_finish_audit_remediation.md`.

## What changed

### Repository hygiene (complete)
- Untracked from the index (ignored going forward): the Reticulum transport
  identity and mesh state under `local_agent/rns_wifi/storage/` and
  `local_agent/tests/rns_offline/storage/`, `local_agent/vendor_tools/platform-tools/`
  (adb/fastboot/sqlite3 binaries), `tools/powerinfer/.hf_cache/`,
  `CHANGELOG/.id_claims/` + lock, root `SYNC_STATUS.json`/`SYNC_LOG.txt`,
  `pasted-text.txt`, `_agent_diff.txt`, `.fuse_hidden*`, `*.pre_*`, `*.bak-*`,
  the two `local_agent/knowledge/retrieval_*.json` caches. 439 files.
- Chats, uploads, render jobs, logs, `ARCHIVE_DECISION.md` and `.claude/*.json`
  are now ignored but deliberately still tracked in this commit, because a
  commit that deletes them would delete them from the workstation on pull.
  `scripts/untrack_private_data.ps1` untracks them locally without touching
  disk; `scripts/sync_down.ps1` snapshots and restores those paths around a
  pull; `scripts/sync_up.ps1` refuses to commit secret/private patterns.
- `.gitignore` now tracks `work/*.py` and `work/*.md` (thermal guard, image
  renderer, scene reasoner) and ignores only `work/runtime/`.
- `requirements.txt`, `requirements-dev.txt`, `requirements-optional.txt`,
  `pyproject.toml` (ruff correctness rules, pytest paths), `conftest.py`
  (skips Windows-only / `work/`-dependent / optional-dependency test modules
  and lists them), `.github/workflows/ci.yml`.
- 44 one-shot codemod scripts moved to `archive/codemods/`; root `atomic_io.py`
  (byte-identical to `local_agent/atomic_io.py`) removed.

### Docs (complete)
- `README.md` rewritten to one page; `CLAUDE.md` reduced to the binding rules
  (old version in `archive/superseded_docs/`); `AGENTS.md` is a pointer;
  `docs/CURRENT_HANDOFF.md` is the single live handoff; `TODO.md` holds the
  live head plus 62 carried-over open items (full file in
  `archive/TODO_closed_2026-09.md`); mojibake repaired in both.
- Equal Shares start prompts → `archive/equal_shares_prompts/`; dated
  handoffs, `GROK_STATUS.md`, `IMPLEMENTATION_STATUS.md` → `archive/handoffs/`;
  the Astra agent's root `CHANGELOG_*`, `EVIDENCE_MATRIX_*`, `FILES_CHANGED*`
  → `CHANGELOG/astra_2026-09/`; Backrooms design notes → `docs/backrooms/`.
- `scripts/write_handoff_status.py` accepts unlettered changelog ids and
  labels its seeded orphan list as a frozen checklist;
  `scripts/build_changelog_index.py` regenerates `CHANGELOG/README.md`.
- `local_agent/README.md` trimmed to product documentation (dated sections in
  `archive/superseded_docs/local_agent_README_history_2026-09.md`).

### Code fixes (partial; see the handoff for exact status)
Five agents worked in parallel on disjoint file sets and were cut off by a
rate limit. Their edits are committed as WIP. Root-pipeline fixes are
complete (notes below). Tools/gates, server/agent and farm/bridge fixes are
largely present; router is half done; `ollama_client.py`, `retrieval.py`,
`farm_offload.py`, `context_compactor.py` are untouched.

## Test evidence (Linux, Python 3.13, requirements-dev installed)

| State | Result |
|---|---|
| Before any code fix (hygiene commit) | 95 failing test ids |
| After the WIP commit | `2074 passed, 96 failed, 33 skipped` |
| New vs. before | 3 new failures (listed in the handoff), 2 old failures fixed |
| New test files from the agents | 13 files, ~2,900 lines; all pass except the two listed |

All 93 remaining failures pre-date this work and are environmental (missing
`dspy`/`torch`/`celery`, `work/image_render.py`, `vendor_sideband/`, Windows
paths), per `AUDIT_2026-11-02.md` §3.

Verification note per CLAUDE.md §3: these are unit-test results. No render was
run; nothing here is verified against a real ComfyUI workflow.

## Pipeline agent notes (verbatim)

# Pipeline fixes (AUDIT_2026-11-02 findings 7, 8, 9, 12 + P2 hygiene)

Branch `claude/epic-hypatia-6mrayy`, repo `/home/user/LocalAIproject`. Only files from the allowed list were touched (the other modified `local_agent/*` files in `git status` belong to the other agents). No git commands run (no `git mv`, see "Could not do"). No `work/`, `outputs/`, lock or owner files were created in the repo.

## Test counts

Command: `<venv>/bin/python -m pytest -p no:cacheprovider -q <files>` from repo root.

| Suite | Before | After |
|---|---|---|
| `test_batch_run_backrooms_gvd.py` + `test_batch_run_backrooms_continuity.py` | 54 passed, 1 failed, 14 subtests | **76 passed, 1 failed, 32 subtests** |
| `test_batch_run_backrooms_gvd.py` alone | 6 passed | 28 passed (22 new) |
| `test_batch_run_backrooms_continuity.py` alone | 48 passed, 1 failed | 48 passed, 1 failed (unchanged) |
| NEW `test_gpu_lock.py` (18) + `test_gvd_watcher.py` (15) + `test_gpu_watchdog.py` (16) + `test_master_batch_runner_state.py` (11) | – | **60 passed, 10 subtests** |

The single failure is pre-existing and unrelated: `RefineCheckpointGraphTests::test_refine_rewires_flux_to_img2img_and_feeds_minimax` asserts a Windows `A:\x\...` path is reduced to its basename, which `Path(...).name` cannot do on Linux. No regressions.

## Per fix

### 1. Status vocabulary (finding 7)
- `batch_run_backrooms_gvd.py:296-369`: `SELECTED_STATUSES`/`LEGACY_DONE_STATUSES`/`DONE_STATUSES`/`FAILED_STATUSES`; `is_selected()` (strict, :308), the ONE `already_done()` (:334: `pipeline_state == "SELECTED"` or `status in {selected,verified,qa_passed,done,ok,success}` or legacy `ok: true` + `video_path`; never for running/error/failed/qa_failed; video must exist > 10 KB), `is_failed()` (:359).
- The continuity chain-source check (`:992`, formerly `already_done(prev_entry)`) now uses strict `is_selected()` so the existing `test_prev_not_selected_falls_back` (legacy `status="done"` must NOT be a chain source) still passes while resume/watcher/keepalive accept legacy `done`. This is the only semantic split; documented in the module comment at :293.
- `gvd_watcher.py:43`: `from batch_run_backrooms_gvd import already_done, is_failed` (local copy deleted). `build_plan()` (:407): `--force-rerun-failed` forces only error/failed/qa_failed entries; stale `running` and never-run clips are planned without `--force`; SELECTED clips skipped unless `--force-all`. `--force-all` (:437-445) prints `FORCE_ALL_WARNING` to stderr, audits `force_all_requested`, and exits 2 without `--yes-overwrite-selected` (new flag, :397).
- `gvd_watcher_keepalive.ps1:30-33`: counts `pipeline_state -eq 'SELECTED' -or status -eq 'selected' -or status -eq 'done'`.
- Tests: `test_batch_run_backrooms_gvd.py::AlreadyDoneVocabularyTests` (4), `test_gvd_watcher.py::VocabularyTests` (2), `::PlanTests` (5, incl. main() refusing/accepting `--force-all`), `::KeepaliveVocabularyTests`.

### 2. Evidence preservation (finding 8)
- `batch_run_backrooms_gvd.py:149-219`: `ATTEMPT_FIELDS`, `attempt_record()`, `record_attempt()` (deduped, uncapped), `begin_attempt()` (merges into existing entry, pushes the prior terminal state onto `attempts`, keeps `video_path`/`vlm_qa`), `finish_render()` (new video replaces old, old kept as `previous_video_path`, stale `vlm_qa` moved to attempts), `fail_entry()` (status=error without dropping anything).
- Main loop: running write :1258 (`begin_attempt`), rendered write :1327 (`finish_render`), qa_failed/selected/auto-selected each call `record_attempt` (:1372, :1381, :1391), error handler :1403 (`fail_entry` on `dict(progress["clips"].get(cid) or {})`).
- VLM QA dump :547 `vlm_qa_dump_paths()` -> `vlm_qa_<id>_<YYYYmmddTHHMMSS>.json` + pointer `vlm_qa_<id>_latest.json` (`{"latest": path, "video_path", "at"}`); written via `atomic_write_json` (:598-607).
- `master_batch_runner.py:709-774 mark_clip`: builds `previous_selected` (video_path, attempt_id, finished_at, verified, status, pipeline_state) from a prior SELECTED state (or carries an existing one) whenever the new status is not SELECTED; `"attempts": attempts` is no longer capped at 5.
- Tests: `EvidencePreservationTests` (5, incl. end-to-end `main()` error-on-rerun keeping `video_path`+`vlm_qa`), `VlmDumpTests`, `test_master_batch_runner_state.py::MarkClipEvidenceTests` (3).

### 3. Shared GPU lock (finding 9)
- NEW `gpu_lock.py`: `GpuLock(holder, purpose, lock_path, owner_path)` = OS byte lock (`msvcrt.locking LK_NBLCK` on `os.name == "nt"`, `fcntl.flock LOCK_EX|LOCK_NB` elsewhere) on `logs/backrooms_batch/runner.lock` + owner JSON `batch_render_queue_owner.json` `{pid, holder, purpose, started_at, started (legacy key), host, lock_path}` written through `local_agent.atomic_io.atomic_write_json`; release writes `{pid: 0, purpose: "released"}` (same files/shape BackroomsWatch used). `pid_alive()` returns True/False/**None** (unknown); `owner_status()` maps unknown -> `"held"`, so **unknown never steals**. `is_held_by_other()` for supervisors (self -> False; probe error -> True, fail closed). `GpuLockHeld` carries the owner record.
- `backrooms_watch.py:13, 84-105, 253-256`: `acquire()` uses `GpuLock('backrooms_watch')` then the unchanged port-8188/ComfyUI-process preflights (lock released if they raise — previously the fd leaked); `close()` releases through the lock. `self.lock_file` still exposed. `from work import thermal_guard` is now lazy (`thermal_guard_module()` / `set_thermal_guard()`, :20-36) so the module imports on a clone/Linux box.
- `gvd_watcher.py:146-205`: `acquire_pid_lock()` acquires the shared `GpuLock("gvd_watcher")` (no more check-then-write); `_pid_alive()` (:153) returns `"unknown"` when the probe fails, and an unknown-liveness owner makes `acquire_pid_lock` exit with "liveness=unknown". `gvd_watcher.pid` is kept only as an informational marker.
- `master_batch_runner.py:1641-1663`: `main()` acquires `GpuLock("master_batch_runner")` before the clip loop (dry-run skips it), returns 3 if held, releases in `finally`.
- `gpu_watchdog.py:201-210`: `render_lock_is_held_by_someone_else()` = `gpu_lock.is_held_by_other()`, exceptions -> True.
- Tests: `test_gpu_lock.py` (18: acquire/release, second holder refused, stale dead pid replaced, unknown never steals, live other refused, ctx manager, owner_status, pid_alive unknown on probe failure, is_held_by_other cases, BackroomsWatch import/inject/acquire-refuse/release-on-preflight-failure), `test_gvd_watcher.py::PidLivenessAndLockTests` (4), `test_master_batch_runner_state.py::GpuLockInMainTests` (3), `test_gpu_watchdog.py::RestartGuardTests::test_render_lock_*` (2).

### 4. Watcher timeout while child is silent
- `gvd_watcher.py:241-250 _pump_stdout` reader thread + `queue.Queue`; `run_clip()` (:252-363) polls `out_q.get(timeout=poll_s)` and checks `time.monotonic() - t0 > timeout_s` every tick, kills the process tree (`_kill_tree`, psutil children when available), audits `clip_timeout`, forces rc 124 if the child somehow exited 0.
- Test: `RunClipTimeoutTests::test_timeout_fires_while_child_is_silent` (real silent child, 1.5 s timeout) and `test_normal_child_output_is_captured_and_rc_passes_through`.

### 5. master_batch_runner TimeoutExpired
- `master_batch_runner.py:146-160 comfy_interrupt()` (urllib POST `/interrupt`, mockable); subprocess loop extracted to `run_generator()` (:1005-1050): `except subprocess.TimeoutExpired` -> `set_attempt_state(db, attempt_id, "FAILED_RENDER")`, `comfy_interrupt()`, synthetic `returncode=124` proc so the normal failed-clip bookkeeping runs and the batch continues (`run_clip` :1300 calls it).
- Tests: `TimeoutTests` (4).

### 6. gpu_watchdog hardening (finding 12)
- `:110-131`: `COMFYUI_STALL_TIMEOUT_SEC = _env_float("GVD_WATCHDOG_STALL_S", 3900.0)` (invalid/<=0 -> default); `GPU_ACTIVE_UTIL_PCT = 5`.
- `:143-158`: `COMFYUI_LAUNCH_CMD` from env (shlex) with **no placeholder**, `COMFYUI_LAUNCH_CWD` from env; `restart_comfyui()` (:213-245) refuses when either is unset or cwd is not a dir and writes `restart_refused_unconfigured` evidence.
- `:267-273` `NvmlGpuMonitor.sample()` wraps `_sample()` in try/except -> `None`; main loop skips `None` samples (:600-603); `shutdown()` guarded.
- `ComfyUiProgressMonitor` (:325-420): `_fetch` works without `requests` (urllib fallback); signature = running prompt ids + pending count + history length/tail + step counter from optional `/progress` or the running item's progress fields (`_step_counter` handles value/max, step/total_steps, current/total, nested `progress`/`status`); `poll(gpu_util_pct=...)` also resets the stall clock when NVML util >= 5 %.
- `:576-577` precedence bug: `if started: state.consecutive_restarts += 1`.
- Logging/`LOG_DIR.mkdir` moved out of import time into `_setup_logging()` (called from `main()`); `pynvml` import no longer raises at import (checked in `NvmlGpuMonitor.__init__`). Log dir default `local_agent/runtime/logs/gpu_watchdog` (env `GVD_WATCHDOG_LOG_DIR`).
- Tests: `test_gpu_watchdog.py` (16).

### 7. vram_controller fail-closed
- `local_agent/vram_controller.py:150-194`: `VramProbeError(RuntimeError)`; `wait_for_vram_headroom()` raises it when nvidia-smi cannot run/parse (was `return` = "assume free"), returns `True` on confirmed headroom, still raises `TimeoutError` otherwise. `release_after_comfyui` (:296) / `release_after_vlm` (:316) mark the owner `comfyui_unverified` / `vlm_unverified` and re-raise.
- `generate_video.py:641-656` caller no longer `except Exception: pass`: prints "VRAM release/headroom NOT verified" and sets `set_vram_owner("comfyui_unverified", ...)`. Rendering still returns the video (it is already saved); the next GPU consumer sees an unverified owner instead of "idle".
- Tests: `VramHeadroomFailClosedTests` (4).

### 8. Atomic writes
- `batch_run_backrooms_gvd.py:121,141-146 save_progress` -> `local_agent.atomic_io.atomic_write_json` (unique temp name; the old shared `progress.tmp` could be raced by the watcher).
- `master_batch_runner.py:46`: local `atomic_write_json` deleted, imported from `local_agent.atomic_io`.
- `backrooms_compile.py:22`: `from local_agent.atomic_io import atomic_write_json` (root `atomic_io.py` can now be deleted; nothing I own imports it).
- Tests: `AtomicProgressTests` (2), `MarkClipEvidenceTests::test_uses_shared_atomic_writer`.

### 9. Codemod residue
- `batch_run_backrooms_gvd.py:390-432`: `wants_literal` (one condition), `pred_from_override` (duplicate `or override.get(...)`, duplicate `elif 'negative_prompt' in override`, duplicate `_lit` conditions, duplicate bypass/literal flags) all deduped; behaviour unchanged (explicit empty `negative_prompt` still does not fall through).
- `generate_video.py:65-67`: `CATEGORY_ALIASES = {_c: _c for _c in CATEGORIES}` (the 8-key dict with 4 duplicate keys was already overwritten by the loop below it).
- `generate_video.py:321-326` (old :330): the `# ...\n    if bool(getattr(pred,'bypass_director'...)...` block was a codemod that landed inside a comment with literal `\n`. Restored intent: default a blank negative to `''` for literal/bypass preds before printing. That is a no-op in `print_plan` (`neg` is already `''` when blank and the function only prints) and the real defaulting already exists in `submit_comfy()` (:553-559), so the dead comment was replaced by a short note rather than resurrected code.
- `generate_video.py:553-554`: the four-way duplicated `bypass_director/literal_prompt` condition deduped to two.
- Tests: `CodemodResidueTests` (2).

### 10. Portability
- `GVD_ROOT` (default `Path(__file__).resolve().parent`): `gvd_watcher.py:24`, `batch_run_backrooms_gvd.py:33`, `master_batch_runner.py:39`, `generate_video.py:33`, `gpu_watchdog.py:106`, `gpu_lock.py:32`, `auto_boot_and_test.py:19`.
- `COMFY_SHARED_INPUT`: `master_batch_runner.py:43` (replaces the :900 literal, now `COMFY_SHARED_INPUT` at :1023); `flux_still_batch.py:31-42` `COMFY_SHARED_INPUT`/`COMFY_SHARED_OUTPUT` (old `COMFY_INPUT`/`COMFY_OUTPUT` still honoured). `auto_boot_and_test.py:20` `COMFY_ROOT` env. `gvd_watcher.py:34` `DEFAULT_PYTHON = GVD_PYTHON or sys.executable` (the `A:\...\Python312\python.exe` literal is gone; the keepalive launches the watcher with that interpreter anyway).
- `gvd_watcher_keepalive.ps1:3-5`: `$root = $env:GVD_ROOT` else `$PSScriptRoot` (script lives in the repo root), `$py = $env:GVD_PYTHON` else the literal.
- Remaining `A:\Users\rhine` literals in my files are only env-var defaults (master_batch_runner :43, flux_still_batch :36/:41, auto_boot_and_test :20, keepalive :5) as the task specified.
- Tests: `PortabilityEnvTests` (2), `test_master_batch_runner_state.py::PortabilityTests`, `KeepaliveVocabularyTests`.

### 11. Timeouts
- `build_long_distinct_master.py:13-14, 40, 92`: `FFPROBE_TIMEOUT_S` (120, env `GVD_FFPROBE_TIMEOUT_S`) and `FFMPEG_TIMEOUT_S` (3600, env `GVD_FFMPEG_TIMEOUT_S`).
- `auto_boot_and_test.py:21, 122-130`: `LIVE_TEST_TIMEOUT_S` (7200, env `GVD_LIVE_TEST_TIMEOUT_S`); `TimeoutExpired` -> rc 124.
- Tests: `SubprocessTimeoutTests` (2).

## Could not do / decisions to flag
- **`git mv gvd_qa.py docs/reference/gvd_qa_reference.py` NOT done.** The audit's "nothing imports it" is wrong: `local_agent/gvd_qa/i2v_gate.py:_runner()` loads `ROOT / "gvd_qa.py"` by file path (the hash-bound I2V receipt gate calls it), as do `local_agent/fresh_review.py:52` and seven `local_agent/test_gvd_qa_*.py` files. Moving it would break the I2V gate and those tests, and `i2v_gate.py` is outside my allowed file list. Consequently the file-path import hacks in `generate_video.py:83-93` and `batch_run_backrooms_gvd.py` (`_load_apply_qa_gate`) were left in place; `test_load_apply_qa_gate_resolves_the_real_function` still passes.
- `already_done()` accepting legacy `done`/`ok`/`success` (per the task) conflicts with the P0-6 rule in the existing continuity test; resolved by keeping the strict check as `is_selected()` for chain-source decisions only (see fix 1). If you prefer the strict rule for resume too, drop `LEGACY_DONE_STATUSES` from `already_done` and the keepalive's `'done'` clause.
- The pre-existing continuity failure (Windows path basename on Linux) was left alone; it is not in the files I was asked to fix beyond test files, and the fix belongs in `video_chain`/graph code.
- `git stash` to re-measure the "before" counts was not run (it would have touched the other agents' uncommitted work); the before numbers come from the run made before any edit.
- Tests requiring `cv2` (`flux_still_batch` -> `creative_still_qa`) stub those modules; `pynvml`/`requests` are absent in the venv and are not needed by the watchdog tests.
