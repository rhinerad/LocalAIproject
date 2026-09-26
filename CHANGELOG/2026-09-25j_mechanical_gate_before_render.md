# 2026-09-25j — GVD live metric: the mechanical gate runs before the render

Follows 2026-09-25i, which found it in the live pass: history row 265 spent
757 s of GPU rendering GVD-B01 `644b` (a clip the sheet review calls good),
then `mechanical_director_gate` rejected the student's `video_prompt` for
lacking a motion keyword ("gradually moves … panning" instead of walk / push
in / tracking / dolly) and the row scored 0.02 without the clip ever reaching
the judge. Operator decision: move the check before the render. The keyword
tables are not relaxed here; that is a separate decision.

No GPU, no VLM, no renders: code and unit tests only.

Backups: `local_agent/{dspy_orchestrator.py,test_dspy_orchestrator.py}.bak_pregate_20260925T094303`.
Edit applied by `local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_pregate.py`
(kept as the record; asserts refuse a second run). `dspy_orchestrator.py`
LF (0 CR before and after); `test_dspy_orchestrator.py` CRLF (0 bare LF
before and after).

## Why it can move

`mechanical_director_gate(example, pred, video_path=None)` reads only the
resolved `start_prompt` / `video_prompt`, the instruction-echo shingles, the
example's `duration_seconds` and category, and the Backrooms camera / motion
keyword tables. Its `video_path` argument was never read (checked line by
line; the docstring now says so). Nothing in it needs the file, so nothing
is lost by running it first.

## Change (`local_agent/dspy_orchestrator.py`, `evaluate_live_candidate`)

- After the existing pre-GPU checks (empty prompt → 0.02, instruction echo →
  0.02) and before `prepare_comfy`: when no `check_fn` is injected, run
  `mechanical_director_gate(example, pred)`; on failure return
  `_fail_result` with `error = "mechanical video check failed: [...]; skipped
  GPU"`. Same leading text as before, so `_fail_penalty` still gives 0.02 and
  history readers keyed on "mechanical video check failed" still match; the
  suffix "; skipped GPU" is the same convention the echo path uses. The row
  carries `video_path: None` and an empty `vram_trace`, as any pre-GPU fail
  does.
- After the render: only an injected `check_fn(video_path, prompt, clip_id)`
  is run now (the test hook, or a future check that actually needs the
  file), with the unchanged failure path (`video_path` set, `vram_trace`
  kept). The built-in gate is no longer called a second time.
- `passes_curriculum()` and `mechanical_director_gate()` themselves are
  unchanged.

What a gated candidate costs the optimizer now: the same 0.02, ~0 s instead
of ~13 min of GPU per occurrence. In the 24o and 25i passes that was 1 of 16
and 1 of 8 candidates respectively.

## Tests (`local_agent/test_dspy_orchestrator.py`, +3 in `LiveMetricFlipFlopTests`)

- A Backrooms pred whose `video_prompt` says "gradually moves … panning" (row
  265's wording) returns 0.02 with "mechanical video check failed", "motion
  keyword" and "skipped GPU" in the error, `video_path` None, and the
  injected `render_fn` / `prepare_comfy` are never called (they `fail()` if
  they are).
- A Backrooms pred with "handheld first-person camcorder walk forward" still
  renders and reaches the VLM with the built-in gate (the `check_fn` stub is
  deleted from the hooks for this test).
- An injected `check_fn` that fails still runs after the render: `render_fn`
  called once, 0.02, `video_path` "ok.mp4", no "skipped GPU", no VLM call.
- `python -m unittest test_dspy_orchestrator test_video_judge test_generalized_video_director test_media_accuracy_gate`: 134 OK.
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
  **1566 OK (2 skipped)**, 353 s, exit 0 (2026-09-25 09:45–09:51 local,
  `runtime/dspy_opt/judge_eval/full_suite_20260925_pregate.log`); 25h's run
  was 1563, +3 tests here.

## Housekeeping

- `TODO.md`: the 25i open item for the gate order closed; the "relax the
  keyword tables" half of that item stays open as its own line.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
