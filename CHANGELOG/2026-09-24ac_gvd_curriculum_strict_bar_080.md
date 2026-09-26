# 2026-09-24ac — GVD curriculum: strict bar 0.85 → 0.80

Follows 2026-09-24q (judge rewrite) and 2026-09-24r (held-out check). Both
left one item as an operator decision: the fixed judge scores correct
Backrooms-batch clips at aesthetic 0.80–0.85, so at the 0.85 strict bar 8 of
12 good held-out clips failed for a scoring-range mismatch, not a defect.
The operator decided: lower the strict bar to 0.80. This entry moves only that
threshold. `video_judge.py` (detector, VLM prompt, caps table),
`dspy_orchestrator.py` and the labels are untouched. No VLM run, no ComfyUI,
no renders: the scores in `results_v2b.jsonl` / `results_heldout_v2b.jsonl`
are re-read against the new bar (the bar is applied in Python after scoring,
so re-scoring would give the same triples).

Backups: `local_agent/{media_accuracy_gate.py,test_media_accuracy_gate.py,gvd_judge_eval.py}.bak_curriculum080_20260924T223830`.

## Where the bar lives

Not in `dspy_orchestrator.py`. `dspy_orchestrator.evaluate_live_candidate`
and `generalized_video_director` both call
`media_accuracy_gate.video_director_passes_curriculum()`, which reads
`media_accuracy_gate._CURRICULUM_STEPS` via `curriculum_threshold(iteration)`
(iteration from `GVD_CURRICULUM_ITERATION`). Steps were
`(0, 0.60), (3, 0.70), (6, 0.80), (9, 0.85)`.

## Why exactly 0.80 (re-derived from the data)

Minimum-axis score of every labeled clip, fixed judge, 8 frames:

| set | good | partial | reject ≥ 0.70 |
|---|---|---|---|
| tuning (50) | 0.80 ×3, 0.85 ×2, 0.90 ×2, 0.95 | 0.40, 0.80 ×2, 0.90 ×2, 0.95 ×2 | 0.80 ×2, 0.85 ×2, 0.90 ×4, 0.95 ×2 |
| held-out (29) | 0.00 ×2, 0.25, 0.80 ×5, 0.85 ×2, 0.90 ×2 | 0.00 ×3, 0.80 ×2 | 0.80, 0.90 |

Scores are quantized to 0.05 and no clip sits between 0.80 and 0.85, so any
bar in (0.80, 0.85] behaves exactly like 0.85 and any bar in (0.60, 0.80]
behaves exactly like 0.80. 0.80 is the only choice that admits the good
Backrooms clips; there is no bar that admits them and still excludes the
three rejects that also score exactly 0.80 (below).

## Change

- `media_accuracy_gate.py` (CRLF kept, verified line by line against the
  backup): `_CURRICULUM_STEPS = ((0, 0.60), (3, 0.70), (6, 0.80))`. The
  `(9, 0.85)` step is gone; iteration 6+ is 0.80 and stays there. Iterations
  0–8 are unchanged.
- `test_media_accuracy_gate.py`: `test_curriculum_tightens_from_060_to_080`
  (was `…_085`), the 0.66-minimum case still fails at iteration 9 with
  threshold 0.80, plus a new `test_curriculum_strict_bar_admits_080_minimum`
  (1.0/1.0/0.80 passes at iteration 99).
- `gvd_judge_eval.py`: `THRESHOLDS = (0.60, 0.80, 0.85)` so `report` shows
  the new strict bar and keeps 0.85 for comparison. Report and run code
  otherwise unchanged.
- Not changed, on purpose: the legacy `VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT` in
  `media_accuracy_gate.py` still says "tightening to 0.85". It is the
  pre-fix judge prompt, kept verbatim so `gvd_judge_eval.py --variant
  baseline` stays a faithful baseline; the production judge (`video_judge.py`)
  has its own prompt, which names no threshold.

## Before / after at the strict bar (`gvd_judge_eval.py report`)

Reports: `runtime/dspy_opt/judge_eval/report_{v2b,heldout_v2b}_curriculum080.json`.
FP = reject clips that pass, FF = good clips that fail; hc = high-confidence labels.

| set | bar | FP | FF | hc FP | hc FF | partial pass |
|---|---|---|---|---|---|---|
| tuning (50) | 0.85 (old) | 8/35 | 3/8 | 4/27 | 2/4 | 4/7 |
| tuning | **0.80 (new)** | 10/35 | **0/8** | 4/27 | **0/4** | 6/7 |
| held-out (29) | 0.85 (old) | 1/12 | 8/12 | 1/7 | 2/5 | 0/5 |
| held-out | **0.80 (new)** | 2/12 | **3/12** | 1/7 | 2/5 | 2/5 |

The 0.60 rows and AUC (0.821 tuning, 0.809 held-out) are unchanged: the
bottom tier was not touched.

Good clips that failed at 0.85 and now pass at 0.80: **8 of 11**.
- tuning, all three: c005, c017, c029 (all 1.0 / 1.0 / 0.80).
- held-out, 5 of 8: c028, c033, c038, br_c002, br_c003 (all 1.0 / 1.0 / 0.80).
- held-out, still failing 3: c004 (0.00, flicker read as a location change),
  c018 (0.25, CPU cut-detector false positive), c035 (0.00, disputed label,
  near-black cap). These are the 24r false fails at 0.60 too; the bar is not
  what fails them.

Reject clips that newly pass at 0.80 (side effect): **3**, all medium
confidence, all scoring exactly 0.80 on the aesthetic axis, and all already
counted as false passes at the 0.60 tier in 24q/24r (so the judge's ranking
of them is unchanged; only the strict tier stops excluding them):
- tuning: GVD-B01 `93fb` (geometry_instability, wall wobble), c036
  (wrong_viewpoint, operator in frame).
- held-out: c021 (color_or_location_drift).
No high-confidence reject newly passes on either set.

Net at the strict tier, both sets combined: false fails 11/20 → 3/20; false
passes 9/47 → 12/47.

## Consequence worth knowing

With the current judge, every clip scores either ≤ 0.40 or ≥ 0.80 on its
minimum axis (the checks fire together, as 24q noted). So today the 0.80
strict tier and the 0.60 base tier accept exactly the same clips on both
labeled sets; the curriculum only tightens again if future judge changes
spread the scores. That is expected and acceptable per the operator's
decision, but it means the curriculum is currently not doing extra work above
iteration 2.

## Tests

- `python -m unittest test_media_accuracy_gate test_video_judge test_generalized_video_director test_dspy_orchestrator`: 115 OK.
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
  **1527 OK (2 skipped)**, 248 s, exit 0 (2026-09-24 22:39–22:43 local)
  (`runtime/dspy_opt/judge_eval/full_suite_20260924_curriculum080.log`).
  24q/24r reported 1496/1497 OK; the count has since grown through other
  sessions' entries (24ab reports 1526) plus this entry's one new test.

## Not done

- The all-zero-score clip ranking below a render timeout (MIPRO 0.0 vs 0.05),
  the other open operator decision from 24q/24r: handled in 2026-09-24ad.
- Future MIPRO scores remain incomparable with history rows ≤ 260 (24q).
