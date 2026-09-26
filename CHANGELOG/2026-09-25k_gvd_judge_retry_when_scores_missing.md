# 2026-09-25k — GVD judge: one retry when the answer arrives without the three scores

Follows 2026-09-25g/h/i, which each left the same item open: a judge answer
that never reaches the three float scores is a `_fail_result` in the live
metric, below every judged clip, for a clip that may be good. The fix named
in all three ("a retry on `missing or invalid float score`") is built here,
measured on the clips that failed, and its two obvious forms (a penalty on
the retry, an anti-repetition note) are rejected by that measurement.

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
29–35 °C at start, 82 °C check before every clip, release and cool-down after
each run). No ComfyUI, no renders; existing files only.

Backups: `local_agent/{video_judge.py,test_video_judge.py,dspy_orchestrator.py,gvd_judge_eval.py}.bak_judgeretry_20260925T101616`.
Edits applied by `local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_judgeretry.py`
(retry, tests) and `_edit_judgeretry_v2.py` (the measured note and penalty;
kept as the record, asserts refuse a second run). All four files LF, 0 CR
before and after.

## 1. What fails (measured in the result files before changing anything)

Two shapes, both `status: fail` from `parse_video_director_scores`:

- **Runaway.** A frame line loops ("more motion blur, slight upward tilt, …")
  until `num_predict=1536` and the JSON never closes → "VLM did not return a
  JSON object with float scores". Tuning D03 `5c73` (v3b and v3c, 8 frames);
  phase C D02 `53ae` offline (25i); and under the 12-frame variants D01
  `6609` (f12) and br_c005 `db78` (heldout_f8c).
- **Closed early.** Frames and checks are written, `constraint_broken` dumps
  the checks, the object closes before the scores → three "missing or invalid
  float score" reasons. Held-out br_c001 `32ce` (v3a, 1536 chars); and at
  `repeat_penalty=1.08` (24ae's results_v2c) D04 `2d86`, D01 `6609`, D04 `cc43`.

What production does with them today, from `_fail_penalty`: a runaway scores
**0.02** (its reason text contains "JSON"), an early close **0.01**. 25i and
TODO said 0.01 for both; 0.02 is the same scalar as a mechanical fail. Either
way the row sits below the 0.10 floor of every judged clip.

They are stochastic on a fixed prompt, which matters for the fix: D03 `5c73`
looped in v3b and v3c and parsed today; D02 `53ae` parsed live (0.92), looped
offline, parsed today (1.00 / 1.00 / 0.90) on the byte-identical prompt;
br_c001 `32ce` closed early once (v3a, 25g's prompt) and parsed in v3b, v3c
and today (25h's prompt). None of the three failed in this session, so the
retry never fired on its own during the measurement (section 3 forces it).

## 2. Change

- `local_agent/video_judge.py`: `JUDGE_RETRY_REPEAT_PENALTY`,
  `JUDGE_RETRY_NUM_PREDICT = 2048`, `JUDGE_RETRY_NOTE`; `scores_missing(parsed)`
  (fail status with a "float score" reason, and not a wrong-model/runtime
  verdict, which no retry can fix); `retry_user_prompt(prompt)` (the first
  attempt's user prompt plus the note).
- `local_agent/dspy_orchestrator.py`, `run_qwen_director_scores`: the call is
  an inner `_ask(user_prompt, num_predict, repeat_penalty, attempt)`; the first
  call is byte-identical to 24ae (1536, 1.0, `json_mode`); if
  `video_judge.scores_missing` the retry runs once with the note,
  `JUDGE_RETRY_NUM_PREDICT` and `JUDGE_RETRY_REPEAT_PENALTY`, and the returned
  dict carries `retry = {attempt: 2, recovered, repeat_penalty, num_predict,
  first_reasons, first_raw_chars, first_raw_tail}`. Every parsed dict now has
  `raw_chars` (true length; `raw` is still cut at 4000). Debug rows in
  `gvd_vlm_raw.jsonl` carry `attempt`. `apply_fault_caps` copies the dict, so
  `retry` reaches `judge_rendered_clip`'s caller.
- `evaluate_live_candidate`: feedback rows gain `judge_retry` (None unless the
  retry produced the verdict); a verdict still without scores after the
  retry fails with the same leading text, `VLM scores rejected: […]; after
  one retry`, so history readers keyed on "VLM scores rejected" still match
  and the penalty is unchanged.
- `local_agent/gvd_judge_eval.py`: result records carry `retry`; the per-clip
  line says `retried`; `summarize` reports `retried` and `retry_recovered`.

## 3. Choosing the retry (two arm sets, 30 scorings, `judge_eval_20260925/retry_arms*.jsonl`)

The arms call the VLM directly with the frames, system prompt, user prompt
and signals `judge_rendered_clip` builds, so the retry is measured even on a
clip whose first answer parses today. `_measure_judgeretry.py`,
`_measure_judgeretry2.py`, logs `run_retry_arms*.log`. Scores are
alignment / temporal / aesthetic after caps.

**Set 1** (157 s): the first draft of the retry, a note that also said "never
repeat a phrase", with the penalty at 1.0 / 1.05 / 1.08, and the penalty
alone.

| clip | label | first attempt (production) | note, 1.0 | note, 1.05 | note, 1.08 | no note, 1.05 |
|---|---|---|---|---|---|---|
| D03 `5c73` | reject | 0.00 / 0.00 / 0.50 | same | same | same | same |
| br_c001 `32ce` | reject | 0.00 / 0.00 / 0.50 | same | 0.20 / 0.25 / 0.75 | **no scores** (982 chars, closed early) | same |
| D02 `53ae` | good | **1.00 / 1.00 / 0.90** | 0.40 / 0.00 / 0.50 | 0.40 / 0.25 / 0.75 | 0.40 / 0.25 / 0.75 | 0.40 / 0.25 / 0.75 |

Two findings. 1.08 closes the JSON early again (24ae's mode, now on the
retry). And every arm turns the good D02 into a reject (`same_place` "no",
`abrupt_cut` "yes", the constraint list quoted as broken), **including the
note at 1.0 with no penalty**: the first attempt wrote eight identical frame
lines and passed; told not to repeat itself, or penalised for it, the VLM
varies near-identical lines and then reads its own variation as change. This
is the mechanism 24ae measured for the penalty ("flips answers by token
frequency, not evidence"), and the note's wording does the same thing.

**Set 2** (106 s): no anti-repetition wording anywhere; two good continuous
clips added as a false-fail guard. Note v2: "the previous answer for these
frames ended before the three scores. Keep each frame line under 15 words.
Close the JSON object only after text_video_alignment, temporal_consistency,
aesthetic_quality and rationale."

| clip | label | first attempt | note v2, 1.0 (**shipped**) | note v2, 1.02 | no frame lines, 1.0 |
|---|---|---|---|---|---|
| D03 `5c73` | reject | 0.00 / 0.00 / 0.50 | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 | 0.30 / 0.25 / 0.40 |
| br_c001 `32ce` | reject | 0.00 / 0.00 / 0.50 | 0.00 / 0.00 / 0.50 | 0.00 / 0.00 / 0.00 | 0.00 / 0.00 / 0.00 |
| D02 `53ae` | good | 1.00 / 1.00 / 0.90 | 0.50 / 0.00 / 0.75 | 0.40 / 0.00 / 0.50 | 0.40 / 0.00 / 0.50 |
| M03 `4110` | good, high | 1.00 / 1.00 / 0.95 (25i) | **1.00 / 1.00 / 0.90** | 1.00 / 1.00 / 0.95 | 0.80 / 0.40 / 0.90 |
| B01 `644b` | good | 1.00 / 1.00 / 0.80 (25i offline) | **1.00 / 1.00 / 0.80** | 0.95 / 0.98 / 0.85 | 0.30 / 0.90 / 0.40 |

- Dropping the per-frame scratchpad (the place a runaway happens) fails both
  good guards: the frame lines are load-bearing for the checks, as 24q
  intended. Rejected.
- The neutral note at 1.0 and at 1.02 keep every reject rejected (5 / 5) and
  both guards at their first-attempt scores (B01 at exactly the 0.80 bar).
  1.02 is untested on the full sets and buys nothing here, so the retry keeps
  the judge's validated sampler: **`JUDGE_RETRY_REPEAT_PENALTY = 1.0`**. The
  escape from a loop is the changed prompt (a different trajectory, on a
  failure that is stochastic on a fixed prompt), not the sampler.
- D02 `53ae` fails under every retry form. Its retry answer is more
  observant than the first attempt's, not less: with short lines the VLM
  writes "F7: FPV breaks into sunlit clearing … F8: aerial view of sunlit
  clearing" (the clip does leave the canopy, which is what the brief asks
  for) and then calls the requested exit a place change and a cut. That is
  the c038 family (a requested camera move read as a cut, 25h Open), not a
  retry defect, and no note wording tried here changes it. In production a
  retried `53ae` would score 0.10–0.35 (judged, above every failure penalty)
  instead of 0.02; it would not recover the 0.92.

## 4. Full sets with the shipped retry

Runner `gvd_judge_eval.py run --variant production` on the shipped code:
tuning (50) → `results_v3d.jsonl`, held-out (29) → `results_heldout_v3d.jsonl`,
the 25i phase C renders (8) → `phaseC_20260925/results_phaseC_v3d.jsonl`;
reports `report_v3d.json`, `report_heldout_v3d.json`,
`phaseC_20260925/report_phaseC_v3d.json`; log
`judge_eval_20260925/run_v3d_chain.log` (10:29–10:43 local, three
llama-server launches, 0 connection resets, 0 crashes, GPU 36–48 °C at start,
~8.5 s per clip). Compared with v3c (25h, the judge before this entry) and
with 25i's offline phase C run by `compare_results.py`.

**The retry fired twice, on two real runaways, and recovered both.**

| set | clip | label | first answer | retry | before |
|---|---|---|---|---|---|
| tuning | D03 `5c73` | reject, high | 6940 chars, no closing brace ("…F5: The motorcycle leans into a right turn, with t") | 0.00 / 0.00 / 0.00, every check failed; 23.1 s for both calls | no scores in v3b and v3c |
| phase C | D02 `53ae` | good, medium | 7493 chars, 25i's loop ("approaching a break in the canopy, slight upward tilt, more motion blur, …") | 0.50 / 0.00 / 0.75, same place "no", cut "yes"; 22.9 s | no scores in 25i's offline run |

So a runaway is not a property of the clip that a changed prompt cannot
escape: both retries parsed at once. In the live metric D03 is now a judged
reject at the 0.10 floor (was 0.02) and D02 a judged false fail at 0.10 (was
0.02, and 0.92 on the day its first answer parsed); neither reaches the bar.
Section 3's caveat on D02 stands.

**Everything else is unchanged.**

| set | bar | v3c (25h) | **v3d** |
|---|---|---|---|
| tuning FP / FF | 0.60 = 0.80 | 8/35 / 0/8 | 8/35 / 0/8 |
| tuning hc FP / hc FF | 0.60 | 4/27 / 0/4 | 4/27 / 0/4 |
| tuning AUC / distinct triples / no-score answers | | 0.843 / 25 / 1 | 0.843 / 25 / **0** |
| held-out FP / FF | 0.60 | 2/12 / 2/12 | 2/12 / 2/12 |
| held-out FF | 0.80 | 3/12 | 3/12 |
| held-out hc FP / hc FF | 0.60 | 1/7 / 0/5 | 1/7 / 0/5 |
| held-out AUC / distinct triples / no-score answers | | 0.833 / 16 / 0 | 0.833 / 16 / 0 |
| phase C FP / FF | 0.60 = 0.80 | 1/5 / 1/3 (25i offline) | 1/5 / 1/3 |
| phase C AUC / no-score answers | | 0.667 / 1 | 0.733 / **0** |

Zero verdict flips at either bar on any set; the reject-faults-passed tables
are identical; and every clip whose first answer parsed has the same min
axis as before (78 of 78 tuning + held-out, 7 of 7 phase C). The first
attempt is byte-identical code, so that last line is a reproducibility
reading, the other face of 25h §5 (4 of 60 differed there): three fresh
server launches and sequential requests today reproduced 85 of 85.

## Tests

- `test_video_judge.py` +10: `JudgeRetryTests` (9): a runaway first answer is
  retried with the note, 2048 tokens and the pinned penalty, and the first
  call's prompt / 1536 / 1.0 are unchanged; a JSON closed before the scores is
  retried; a parsed first answer is not; a second failure is final (two
  calls, `recovered` False); a wrong-runtime verdict is not retried;
  `scores_missing` on each reason shape; the `retry` dict survives
  `apply_fault_caps` and reaches `judge_retry` in the feedback row; a failed
  retry is named in the live-metric error with the same penalty; the sampler
  and note are pinned to the measured decision (1.0, no "repeat" wording,
  "under 15 words"). `EvalReportTests` +1 (`retried` / `retry_recovered`).
  The retry tests patch `dspy_orchestrator.HERE` to a temp dir and assert one
  dump row per call, so they no longer append synthetic rows to
  `gvd_vlm_raw.jsonl` (the older `test_judge_vlm_call_sends_repeat_penalty_off`
  still writes one per run; left as is).
- `python -m unittest test_video_judge`: 50 OK (40 before).
- `python -m unittest test_video_judge test_dspy_orchestrator test_media_accuracy_gate test_generalized_video_director test_llama_cpp_client`: 149 OK.
- Full non-live suite: `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')` on the
  final files: **1576 OK (2 skipped)**, 357 s, exit 0 (2026-09-25 10:43–10:50
  local, `runtime/dspy_opt/judge_eval/full_suite_20260925_judgeretry.log`);
  25j's run was 1566, +10 tests here. Run after the VLM was released, not
  beside it.

## Housekeeping

- `gvd_vlm_raw.jsonl`: gained 121 rows (929 → 1050 at the time of writing; the pre-existing test adds one per run). 92 are this entry's calls through `run_qwen_director_scores` (3 production rows in arm set 1, 87 first attempts, 2 retries marked `attempt: 2`); the direct arm calls in `_measure_judgeretry*.py` bypass the dump. 29 are synthetic rows from unit-test runs before the retry tests were pointed at a temp dir (24 from the new tests, 9 of them `attempt: 2`, and 5 from the pre-existing test).
- `gvd_live_metric_history.jsonl` untouched (269 rows).
- `TODO.md`: the runaway / parse-failure item closed with this outcome; the
  non-determinism item reworded (the retry exists; the ±0.05 noise and the
  0.80-bar margin remain).
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- Two runaways recurred in the full sets and both retries recovered (section
  4); the arm sets (section 3) could not show that because none recurred
  there. Two of two is the evidence so far. The first occurrence in a live
  MIPRO row will show as `judge_retry` in the history; check `recovered`.
- D02 `53ae` under any retry, and c038: a requested camera move or exit read
  as a cut. The measured camera-motion estimator (25c/e) marking a pan / turn
  / climb window in the user prompt, the way `dark_spans_s` marks a dip, is
  still the next thing to try; not started.
- Whether to relax the Backrooms motion-keyword table (25i/25j): operator
  decision, untouched.
