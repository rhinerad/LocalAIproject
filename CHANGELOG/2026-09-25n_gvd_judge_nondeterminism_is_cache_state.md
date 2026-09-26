# 2026-09-25n — GVD judge non-determinism, measured: a deterministic judge whose answer depends on llama-server's prompt-cache state; the live metric judges cold, the eval runner has judged warm since 24q

Follows 2026-09-25h (§5: "4 of 60 byte-identical prompts came back
different", one aesthetic 0.80 → 0.75), 25i (rows 263 and 267 disagreed with
their offline re-judge on byte-identical prompts), 25k (85/85 reproduced) and
25l. TODO item: measure before proposing anything. Measured: **262
judgements over 9 llama-server launches**, every one through the production
path (`gvd_judge_eval.judge_production` → `dspy_orchestrator.judge_rendered_clip`),
plus the free evidence already on disk. **No production code changed in this
entry**; the remedy is written up as an operator decision (section 8).

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
≤ 70 °C at start; owner held; 82 °C check before every call; release and
cool-down after each launch). Three background chains, nine launches,
preflight GPU 30 / 48 / 48 / 47 / 48 °C (11:36:08–11:59:47), 45 / 47 °C
(11:59:55–12:11:01), 44 / 47 °C (12:11:14–12:20:29 local). **1 connection
reset** (r2, br_c007: the runner's server log ends mid-request after 16
tasks with no error line, the 24q "cause unknown" mode; the production
launch path relaunched at 11:38:50 and served the remaining 15 requests), 4
judge retries (below), 0 crashes otherwise. GPU 44 °C / 39 MiB afterwards,
8188 and 11436 closed, owner released. ~9.6 s per clip cold, ~10 s warm. No
ComfyUI, no renders; existing files only.

Scripts (kept as the record): `local_agent/runtime/dspy_opt/judge_eval_20260925/_measure_nondet.py`
(one launch per invocation; `--set/--order/--passes`, `--targets`, `--extra`,
and `--cache-prompt off`, a **measurement-only, process-local** patch that
forwards `cache_prompt: false` on every judge request), `_analyze_nondet.py`
→ `nondet_summary.{txt,json}`, `_edit_todo_nondet.py`. Results:
`runtime/dspy_opt/judge_eval/results_heldout_v3e_{r2,r3}.jsonl`,
`judge_eval_20260925/nondet_{heldout_reverse,first_7d15,first_53ae,heldout_nocache_a,heldout_nocache_b,phaseC_nocache,tuning_nocache}.jsonl`
(+ `.llama_server.log` each), logs `run_nondet_{chain,cold_chain,cold2_chain}.log`.

## 1. Free evidence first (no GPU)

- v3c (25h), v3d (25k) and v3e (25l) are three separate launches on
  byte-identical prompts for 69 clips (46 tuning + 23 held-out, the ones 25l
  did not mark): **raw text identical 69/69**, so the noise is not a steady
  per-request rate.
- 25h's v3b → v3c: recounted at raw-text level, **8 of 60** prompt-identical
  clips differed (25h counted the 4 with check or score changes). v3b is the
  one run with a mid-run server relaunch (the D05 connection reset at
  position 4); the six tuning differences sit at positions 5 (D05's own
  retry, the new server's first request), 29, 31, 32, 38, 46. The
  divergence in each pair is a single near-tie word deep in a frame line or
  rationale ("Distant view of cliffs" vs "View of cliffs"; "black lizard" vs
  "dark lizard"), after which the rest of the answer re-converges or not.
- The production launch (`dspy_optimizer._ensure_owned_qwen25_vl_runtime`)
  and the runner's launch use the same arguments (ctx 32768, all layers on
  GPU, `--image-min-tokens 1024`, `--flash-attn auto`), so launch flags are
  not a live-vs-offline difference.

## 2. What the server does (its own log)

For every request after the first in a launch: `selected slot by LCP
similarity, f_sim_best = 0.130, f_keep = 0.124` and `prompt eval … 9271
tokens` of ~11 200: the slot keeps the shared prefix (the system prompt's
KV, computed inside the **first** request's batch) and prefills only the
rest. The first request prefills everything (10 660 tokens). A prompt-cache
of finished slots is kept in host memory ("making room for prompt cache
entry, removing oldest entry, 1.5 GiB"), so a request identical to a recent
one is restored almost whole. Three conditions therefore exist, and each
live MIPRO judgement is the first of them (the VLM is launched per candidate
and released after it, 25i):

| condition | what is prefilled | where it occurs |
|---|---|---|
| **cold** | the whole prompt, in its own batch | the live metric, every time; clip 1 of every eval run |
| **warm-prefix** | everything but the system prompt, whose KV came from the launch's first request | every eval-runner clip after the first |
| **warm-full** | the generated tokens only, the prompt restored from the cache | back-to-back repeats of one clip (never production) |

## 3. Measured (held-out 29 unless stated; "identical" = byte-identical raw text)

| comparison | condition | raw | checks | scores | min axis | verdict flips 0.60 / 0.80 |
|---|---|---|---|---|---|---|
| A. v3e vs r3 (two launches, label order) | warm-prefix, same history | **29/29** | 29 | 29 | 29 | 0 / 0 |
| A. v3e vs r2 (r2 relaunched at clip 16) | warm-prefix, history differs from clip 16 | 15/29: **15/15 before, 0/14 after** | 26 | 23 | 26 | 0 / 0 |
| B. reversed order vs v3e | warm-prefix, different history | 2/29 | 23 | 23 | 25 | 0 / 0 |
| C. reversed pass 2 vs pass 1 (one launch) | warm-prefix, same history | 28/29 (the exception is pass 1's cold clip 1) | 28 | 28 | 29 | 0 / 0 |
| H. cold a vs cold b (two launches) | **cold** | **29/29** | 29 | 29 | 29 | 0 / 0 |
| H/J. cold vs warm v3e | cold vs warm-prefix | 3/29 | 22 | 19 | 23 | 0 / **1** (c028) |
| J. cold vs warm v3e, tuning (50) | cold vs warm-prefix | 2/50 | 39 | 37 | 42 | **3 / 3** |

- A clip judged cold is the same across launches: c001 (clip 1 of every
  label-order run) 5/5 launches identical; D02 `715d` (clip 1 of the
  reversed pass, plus both cold arms) 3/3.
- D. Back-to-back repeats within one launch (warm-full), six goods at or
  near the bar, five judgements each: c028 0.75 ×3 then 0.80 ×2; c018 0.90
  ×2 then 0.80 ×3; **c038 0.85, 0.85, 0.00, 0.85, 0.85** (the 0.00 is the
  pre-25l answer shape: subject "no", same place "no", cut "yes"); c033,
  br_c002, br_c003 unchanged. Wording differed on every clip; the verdict on
  two.
- E. First request of a fresh launch (the live position): **D02 `7d15`
  cold = 0.40 / 0.25 / 0.75, the 25i live scores exactly** (row 267); warm
  in another launch = 0.95 / 0.95 / 0.80, the offline pass. **D02 `53ae`
  cold = 1.00 / 1.00 / 0.90, the live scores** (row 263); warm after D01
  `167c` (label order) it loops and is retried; warm after `7d15` it parses
  at 0.90.
- I. **Phase C cold offline vs live rows 262–269: 7 of 7 live-judged rows
  identical in all three scores and all eight checks**; the eighth (B01
  `644b`, never judged live) 1.00 / 1.00 / 0.80 as offline. The live metric
  is deterministic and reproducible offline, in the cold condition only.
- Retries: 25k's retry fired 4 times, all recovered: `715d` (runaway, r2
  after the relaunch), br_c001 `32ce` (JSON closed early in **both**
  reversed passes at the same state: the failure is a function of the
  state, not chance). Cold: **0 no-score answers in 116 cold judgements**
  (D03 `5c73`, which looped in every warm label-order run since 25h, wrote
  2 732 chars and parsed).

## 4. Labeled-set metrics under production's condition (cold) vs the warm numbers reported since 24q

| set | bar | FP warm → cold | FF warm → cold | hc FP | hc FF | AUC |
|---|---|---|---|---|---|---|
| tuning (50) | 0.60 = 0.80 | 7/35 → **8/35** | 0/8 → 0/8 | 3/27 → 4/27 | 0/4 → 0/4 | 0.864 → 0.852 |
| held-out (29) | 0.60 | 2/12 → 2/12 | 1/12 → 1/12 | 1/7 → 1/7 | 0/5 → 0/5 | 0.872 → 0.861 |
| held-out | 0.80 | 2/12 → 2/12 | 2/12 → **1/12** | 1/7 → 1/7 | 0/5 → 0/5 | |

The four verdicts that differ: tuning D01 `086a` (reject, late drift: 0.30
warm → **0.95 cold**, the 25h catch is a warm-only catch), B01 `3172`
(reject, walls turn green: 0.30 → **0.80**), c030 (reject: 0.85 warm → **0.00
cold**, caught cold), held-out c028 (good: 0.75 → **0.80**, clears the bar
cold). Reject faults passed at 0.60, cold: tuning hard_cut **0/10** (1/10
warm), location_drift 1/4 (`086a` instead of c030), scene_change 0/4,
color_or_location_drift **1/1** (`3172`, 0/1 warm); held-out hard_cut 0/3,
location_drift 0/4, unchanged. Every 24q–25l number was a warm-prefix
measurement: a close proxy for the production judge (±1 clip per set on
every rate), not the thing itself.

## 5. What the earlier observations were

- 25h §5 ("4 of 60"): v3b's mid-run relaunch. r2 reproduced the pattern
  today: identical before the relaunch (15/15), different after (14/14).
- 24ae's "13 re-judged clips identical" and 25k's "85 of 85": same launch
  history, so identical by construction; not evidence about production.
- 25i's rows 263 / 267 vs their offline re-judge: cold vs warm, now
  reproduced both ways (section 3 E, I).
- 25k's runaways and 25g's early close: state-dependent, not random; the
  retry (a changed prompt = a different state) remains the right safety net
  and fired 4/4 successfully here.

## 6. The bar, from the data

Only one clip on either labeled set has a warm minimum axis in [0.60, 0.80):
c028 at 0.75 (good). Cold, c028 is 0.80 and nothing sits in that interval.
So a 0.75 bar would admit c028 warm and no reject, and change nothing cold.
Three goods sit at exactly 0.80 in every judgement, cold and warm (br_c002
8/8, br_c003 8/8, tuning c017 in both conditions) and c018 in 6 of 8: the
missing margin is a property of the judge's aesthetic scale on Backrooms
clips (24ac), not of noise.

## 7. Decision rules simulated (held-out labels, expected counts)

From all 163 warm judgements collected (5–8 per clip, mixed histories):
single sample at 0.80: false pass 2.00/12, false fail 1.88/12; either-of-two
1.54; both-of-two 2.21; mean-of-two ≥ 0.80 2.21, ≥ 0.775 1.79;
majority-of-three 1.89; single at 0.75 1.12; at 0.60 1.12. From the cold
judgements: every rule gives false pass 2/12 (c021, M04 `4c83`), false fail
1/12 (c035, disputed label), because the two cold samples are identical.
Two-sample judging buys at most 0.35 expected false fails on 12 goods for
double the VLM time under warm, and nothing under cold.

## 8. Operator decision (not applied here)

Recommended: **judge cold everywhere.** Send `cache_prompt: false` on the
judge's request: one entry in `llama_cpp_client._SAMPLER_FIELDS`
(`("cache_prompt", bool)`), one keyword through `media_tools._run_vision_gpu`
from `dspy_orchestrator.run_qwen_director_scores` (first attempt and retry),
plus tests. Production is unchanged in effect (already cold, and protected
against any future warm-up call); the eval runner then measures the
production judge, deterministic and history-independent, at ~+0.3 s per
clip (a 10.6k-token prefill instead of 9.3k). Re-baseline on the cold
results already on disk (`nondet_tuning_nocache.jsonl`,
`nondet_heldout_nocache_a.jsonl`; section 4). Alternatives, for the record:
warming production with a fixed prefill would move it to the condition where
`7d15` passes and `53ae` loops; two-sample judging (section 7) and a 0.75
bar (section 6) address a noise that does not exist cold.

## Tests

No production file changed; `video_judge.py`, `dspy_orchestrator.py`,
`llama_cpp_client.py`, `media_tools.py` are as 25l left them (the
`cache_prompt` patch lives in `_measure_nondet.py` and applies only to that
process). The full non-live suite therefore stands at 25l's **1582 OK (2
skipped)**; not re-run.

## Housekeeping

- `gvd_vlm_raw.jsonl` 1144 → 1409 (262 judgements + 3 retry rows; the
  connection-reset request left no row). `gvd_live_metric_history.jsonl`
  untouched (269 rows).
- `TODO.md` (CRLF): the "not bit-deterministic" item closed with this
  finding; an operator-decision item added; 25n added to the evidence list.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
- `CHANGELOG/.id_claims/2026-09-25m` remains a stray claim (25l); this entry
  is 25n.

## Open

- The connection reset (24q "cause unknown", now four occurrences: v2a ×4,
  v3b D05, r2 br_c007) kills the server silently: the runner's log ends
  after "processing task" with no error line. The relaunch is handled; the
  cause is still not in any log.
- If the operator takes the recommendation, 25l's c038 fix and 25h's
  flicker fixes hold cold (c038 0.85 in both cold arms; c004 0.85, c018
  0.80), while the late-drift catch on D01 `086a` (25h) does not (0.95 cold);
  the cold baseline in section 4 is the honest starting point.
- Warm-full repeats (section 3 D) show that the 25l turn mark is not what
  keeps c038 up under every state; it is under the production state.
