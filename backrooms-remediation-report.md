# Backrooms pipeline — remediation report and updated verdict

**Scope:** `COMFYUI_STORY_HANDOFF_2026-08-09` (confirmed by you as the live pipeline). This report covers the remediation pass performed after the original readiness audit (`backrooms-readiness-audit.md`), which concluded **NO-GO** and listed a 10-item minimal fix set. All code changes below were made directly in that live folder, per your instruction to "get this to a full go."

**Safety posture, unchanged throughout:** no live ComfyUI calls, no model loads, no GPU use, no real renders were performed at any point in this remediation pass. Every fix is verified by new or updated **offline, mocked unit tests** only. This is the same constraint the original audit operated under; only the "do not modify production code" part of the original constraint was lifted, by your explicit request.

---

## 1. Fix-set items, one by one

| # | Audit item | Status | What was actually done |
|---|---|---|---|
| 1 | Gate `batch_run_backrooms_gvd.py` before `submit_comfy()` | **Done** | Added `gate_before_video_submit()`, called immediately before every video submission. Fails closed by default; requires `--allow-ungated-i2v` or a valid QA receipt. 6 new tests (`test_batch_run_backrooms_gvd.py`). |
| 2 | Cover GVD execution tools with the same gate | **Done** | `local_agent/tools.py`: extended `_VIDEO_TOOLS_NEEDING_STILL_APPROVAL`. `gvd_tool_router/service.py`: `execute_tool()` now reads `operator_approved_i2v` from the raw manifest dict *before* schema stripping and fails closed for every video tool (stills exempt) — so the gate can't be bypassed by calling the router directly. 4 new tests. |
| 3 | Make QA evaluator fail-closed, not fail-open | **Done** | `gvd_qa/evaluate.py`: added fail-closed branches for a missing/unreadable artifact and for no QA evidence at all; both route to `hold_review`, never `accept`. 4 new tests. |
| 4 | Wire `prior_artifacts` into the QA loop; guarantee VLM release | **Done** | `gvd_qa/loop.py`: `run_qa_loop()` now threads `prior_artifacts`/`artifact_bytes` into `evaluate_fn`, and the render→evaluate body is wrapped in `try/finally` so `finish_validate(release_vlm)` always runs, even on a raised exception. 2 new tests. |
| 5 | Fix GPU lease reentrancy; make execute_tool's lease scope cover completion | **Done, by a different mechanism than literally suggested** | `gpu_lease.py`: added a `holders` refcount to the lease JSON for correct same-PID nested acquire/release (LIFO) semantics. I deliberately did **not** widen the underlying OS lock's held duration — that would have broken the existing `heartbeat()` mechanism. Instead, `service.py`'s `execute_tool()` now holds the lease until the render reaches a terminal state: a new `_wait_for_stage_completion()` bounded-poll loop (via `reconcile()`, injectable `sleep_fn`/`time_fn`, hard timeout with an explicit `timed_out_waiting_for_completion` marker — never hangs forever) runs inside the `with acquire(...) as lease:` block. 4 new dedicated tests plus 3 existing `live=True` tests updated to pass `wait_for_completion=False` where they're only exercising submission, not completion. |
| 6 | `RETRY_PENDING` in `find_open_attempt()`; `add_shot()` upsert | **Done** | `store.py`: `find_open_attempt()` now matches `RETRY_PENDING`; `add_shot()` is `INSERT ... ON CONFLICT(shot_id) DO UPDATE`, so a crash-and-resume no longer raises a `UNIQUE constraint` error. 3 new tests. |
| 7 | Give `reconcile()` a genuine terminal-error branch | **Done** | `executor.py`: added a `_queue_membership()` helper and a real terminal branch — an explicit ComfyUI error status, or a prompt_id positively absent from both `/history` and `/queue`, now returns `FAILED` instead of `RUNNING` forever; an unreadable `/queue` stays conservatively `RUNNING`. 5 new tests. |
| 8 | Consolidate on `production_store.py`'s stronger discipline, or retire `gvd_tool_router/store.py`'s weaker semantics | **Not done** | This is an architectural consolidation, not a bug fix, and I judged it out of scope for a same-day remediation pass verified only by offline tests — swapping the storage layer underneath the GVD execution path is a much larger change I did not want to make without a live smoke-test available. The concrete symptoms this item was really about (global `shot_id` crash, invisible `RETRY_PENDING` attempts) **are** fixed, via item 6 above. The broader "which store is canonical" question is still open. |
| 9 | `scene_reasoner.py`: validate LoRAs/character IDs, fix the eviction note, wrap in try/finally | **Done** | `_parse_decision()` now checks every `loras` entry and every `reference_character_ids` entry against the real registries (`available_options()`) and forces operator review on anything invented or unregistered, regardless of reported confidence. `reason_about_shot()`'s note is now conditioned on `eviction["verified"]` instead of unconditionally claiming success. `decide_shot()` is now wrapped in `try/finally` so `evict_reasoning_model()` always runs, even on a raised exception. 17 new tests (this module had zero coverage before). **The module remains disabled and unwired from any render path** — this fix makes it safe to consider enabling later; it does not enable it. |
| 10 | Hard cap on the `while not accepted:` retry loop; general watchdog-driven hang termination | **Partially done** | Added an unconditional hard cap (`still_retry_cap_reached()` / `max_still_retry_attempts()`, default 200, overridable via `PROMPT_PACK_MAX_STILL_RETRIES`) that fires regardless of which recovery path is active — the existing recovery-specific bounds (e.g. `apply_identity_pose_recovery`'s own 96-attempt range) stay untouched, and 200 was chosen specifically to sit above all of them. On trip, it pauses the run cleanly (`paused_for_operator_review`, evidence preserved) using the same pattern already used elsewhere in this file, rather than crashing or looping. 5 new tests. **The second half — general watchdog-driven hang termination — was not built.** The existing watchdog-subprocess/log mechanism is unchanged; a true hang-detection layer (distinct from a retry-count cap) would be a larger addition I judged as better done as its own explicitly-scoped follow-up. |

---

## 2. Full offline test suite — final status

Every module this remediation pass touched is green:

- `local_agent/test_gvd_tool_router.py` — **46/46 passing** (42 pre-existing + 4 new for the lease/completion fix)
- `local_agent/test_gvd_qa.py` — **15/15 passing**
- `test_batch_run_backrooms_gvd.py` — **6/6 passing**
- `work/test_scene_reasoner.py` — **17/17 passing** (new file; this module had no test coverage before this pass)
- `work/test_still_retry_not_stop.py` — **94/121 passing**, 27 errors, all pre-existing and environment-only (see below), 0 new failures from the retry-cap change

I also re-ran the full repository test tree (139 modules, ~1,564 tests) as a final cross-check. Every failure or error outside the files this pass touched is attributable to this sandbox not matching the real Windows production machine, not to any change made here:

- `hashlib.file_digest` missing (needs Python 3.11+; this sandbox runs 3.10.12)
- `datetime.UTC` missing (same Python-version gap)
- `torch`, `dspy` not installed in this sandbox
- A hardcoded Windows `ffmpeg.exe` path under `AppData\Local\Microsoft\WinGet\...` that only exists on your machine
- Windows-style absolute paths (`A:\Users\rhine\...`) that Linux's `pathlib` misreads as one long filename, tripping a `File name too long` OSError
- A few pre-existing, apparently-stale tests unrelated to this scope (e.g. `test_dspy_orchestrator` expecting a retired `build_wan_graph` function, or asserting `denoise == 0.90` where the code now returns `1.0`)

None of these touch `gvd_tool_router/`, `gvd_qa/evaluate.py` or `loop.py`, `tools.py`'s approval gate, `generate_video.py`, `batch_run_backrooms_gvd.py`, `scene_reasoner.py`, or the retry-cap change in `run_prompt_pack_production.py`. I did not attempt to fix any of this unrelated environment noise — it was present before this session's changes and is out of scope for this remediation pass.

---

## 3. Updated verdict

**The four findings that drove the original NO-GO are now fixed and covered by new offline tests:**

- (a) the batch entry point (`batch_run_backrooms_gvd.py`) had no QA/approval code at all → now gated, fail-closed, and gate-coverage can't be bypassed via the router directly either.
- (b) the QA evaluator was fail-open when the VLM was unavailable → now fail-closed on a missing artifact or no evidence.
- (c) GPU exclusivity didn't actually hold across ownership mechanisms → the specific reentrancy bug is fixed, and the lease is now held until the render completes (bounded, never hangs).
- (d) the recovery/resume layer had a crash-resubmission gap and a global-uniqueness crash mode → both fixed and tested.

Two items from the fix set remain **explicitly open, by deliberate choice, and are not correctness bugs**: consolidating onto a single store implementation (item 8), and building a general watchdog/hang-detection layer beyond the new hard retry cap (the second half of item 10). Neither was a cited cause of the original NO-GO on its own.

Given all of the above, I'd call this: **GO for the specific findings this audit raised, with two caveats** — (1) none of this has ever been exercised against a live ComfyUI instance or a real render, since that stayed out of scope for both the audit and this remediation pass; a short live smoke test (one still, one video, through the actual gate) before your first unattended run would be the responsible next step, not a formality. (2) the two explicitly-deferred items above are real, tracked gaps, not resolved ones — they just aren't the ones that were blocking a go.

`scene_reasoner.py` stays disabled and unwired, as recommended in the original audit; its fixes only make it safer to consider enabling later.
