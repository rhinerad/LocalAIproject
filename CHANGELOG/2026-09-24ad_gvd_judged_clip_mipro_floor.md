# 2026-09-24ad — GVD live metric: judged clips floored above every failure penalty

Follows 2026-09-24ac (strict bar 0.80). This closes the second open operator
decision from 2026-09-24q/r: a rendered clip that the judge scored all-zero
got MIPRO scalar 0.0, **below** a render timeout (0.05), a mechanical /
prompt-format failure (0.02) and a pipeline failure (0.01). Near-zero verdicts
collided too: 0.0/0.0/0.15 gives 0.7·0 + 0.3·0.05 = 0.045, under the timeout.
So the optimizer could prefer a program that never renders over one that
renders a bad clip, and the fixed judge returns all-zero far more often than
the old one did (24q). No VLM run, no ComfyUI, no renders: read-only analysis
of existing results plus unit tests.

Backups: `local_agent/{dspy_orchestrator.py,test_dspy_orchestrator.py}.bak_judgedfloor_20260924T223830`.

## Change (`local_agent/dspy_orchestrator.py`, LF kept)

- New `JUDGED_SCORE_FLOOR = 0.10` and `_judged_scalar(minimum, mean)` =
  `max(0.10, 0.7·min + 0.3·mean)`, next to `_fail_penalty`. 0.10 is twice the
  largest failure penalty.
- `evaluate_live_candidate` uses it for the judged-clip `mipro`. The feedback
  row gains `mipro_raw` (the unfloored value) so history keeps the judge's
  full ranking; `mipro_raw` and `mipro` differ only below 0.10.
- A clamp, not a rescale: every judged clip scoring ≥ 0.10 keeps exactly the
  scalar it had, so the 24q statement "the 0.7·min + 0.3·mean MIPRO scalar is
  unchanged" still holds for everything that was ranking correctly. The
  ordering "any judged clip > any failure" now holds by construction.
- Failure penalties (0.05 / 0.02 / 0.01), the curriculum, `passes_curriculum`
  and the judge itself are untouched. A floored all-zero clip still has
  `passes_curriculum = False`.
- Not changed: the mock path in `generalized_video_director.py` uses
  `mipro = minimum` with failure = 0.0; it has no timeout penalty so it has no
  inversion, and it never produces all-zero scores. `gvd_judge_eval.py`'s AUC
  still uses the raw scalar, on purpose: it measures the judge's ranking, and
  the floor is an optimizer concern. With the floor the only effect on AUC
  would be ties among the bottom rejects.

## Effect on the labeled sets (raw scalar, `results_v2b` / `results_heldout_v2b`)

| set | judged clips | raw < 0.10 (now 0.10) | of which ≤ 0.05 (tied with / under a timeout) | all-zero | good clips moved |
|---|---|---|---|---|---|
| tuning (50) | 50 | 18 (all reject) | 17 | 9 | 0 (lowest good 0.84) |
| held-out (29) | 29 | 6 (5 reject, 1 partial) | 6 | 2 | 0 (lowest good exactly 0.10: c004, c035) |

So on these sets 23 of 79 real renders used to rank at or below a timeout;
none does now, and no good clip's scalar changes.

## What the live history shows (`runtime/dspy_opt/gvd_live_metric_history.jsonl`, 261 rows, read only)

Of 201 non-mock judged rows, **138 have minimum 0.0 and `mipro` 0.0**, while
the 60 failure rows include 15 timeouts at 0.05, 6 mechanical at 0.02 and 17
pipeline at 0.01. So under the old judge and scalar, roughly two thirds of
every real render the optimizer ever saw ranked below a timeout. Caveat:
those rows were written by the pre-fix judge and an older scalar (one row has
mean 0.11 with `mipro` 0.0, i.e. `mipro = minimum` at the time), so the
figure shows how common the collision was, not what the current formula
would have produced.

## Why a floor rather than lowering the penalties

Lowering the penalties (e.g. timeout 0.005) would keep the all-zero clip at
0.0, still the worst possible outcome, tied with nothing but itself. The
operator's framing in 24q is that a rendered and judged clip carries
information a timeout does not, so the fix has to lift judged clips, not push
failures down. The floor also leaves the three failure modes distinguishable
from each other, which is what `_fail_penalty` exists for.

## Tests

- `test_dspy_orchestrator.py` +2: an all-zero judged clip (legacy two-arg
  judge hook) returns exactly `JUDGED_SCORE_FLOOR`, exceeds every
  `_fail_penalty` string, records `mipro_raw = 0.0` and still fails the
  curriculum; `_judged_scalar` lifts 0.0/0.0 and 0.0/0.15 (raw 0.045) to
  0.10 and leaves 0.30/0.6833, 0.74/0.7867 and 1.0/1.0 unchanged. Existing
  scalar assertions in `test_dspy_orchestrator.py` and `test_video_judge.py`
  (all ≥ 0.10) pass unchanged. CRLF kept in the test file.
- `python -m unittest test_dspy_orchestrator test_video_judge test_generalized_video_director test_media_accuracy_gate`: 117 OK.
- Full non-live suite, `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`:
  **1529 OK (2 skipped)**, 247 s, exit 0 (2026-09-24 22:50–22:55 local)
  (`runtime/dspy_opt/judge_eval/full_suite_20260924_judgedfloor.log`).
  24ac reported 1527; +2 tests here.

## Open

- History rows ≤ 260 were written by the old judge and are not comparable
  anyway (24q); rows from now on carry both `mipro` and `mipro_raw`.
- The next real MIPRO run is the first that exercises the floor in anger.
