# 2026-09-25o — GVD judge: cold prefill on every call (`cache_prompt: false`); re-baselined, byte-identical to the 25n cold measurements and to the live rows

Follows 2026-09-25n, which measured that the judge's answer depends on
llama-server's prompt-cache state: the live metric always judges cold (a
fresh launch per candidate, the whole prompt prefilled), the eval runner has
judged warm since 24q (the system prompt's KV kept from the launch's first
request), the two differ in wording on ~90% of clips and in verdict on 4/79
labeled clips plus two phase C renders, and each condition alone is
byte-reproducible. Operator decision: judge cold everywhere and re-baseline.
Applied here; the re-baseline is the last section's table.

VLM only, under `gvd_judge_eval.preflight` (8188 closed, owners idle, GPU
≤ 70 °C at start; owner held; 82 °C check before every clip; release and
cool-down after each run). Three launches, preflight GPU 29 / 48 / 47 °C,
12:43:28–12:58:44 local, **0 connection resets, 0 crashes, 0 retries, 0
no-score answers**, GPU 41 °C / 39 MiB afterwards, 8188 and 11436 closed,
owner released. ~9.3 s (tuning) / 9.9 s (held-out) per clip, the same as
warm within noise (a full 10.5k-token prefill instead of 9.3k). No ComfyUI,
no renders; existing files only.

Backups: `local_agent/{llama_cpp_client.py,media_tools.py,video_judge.py,dspy_orchestrator.py,test_llama_cpp_client.py,test_media_analysis.py,test_video_judge.py}.bak_coldjudge_20260925T124103`,
`TODO.md.bak_gvd_judge_coldjudge_20260925T130727`. Code and tests applied by
`local_agent/runtime/dspy_opt/judge_eval_20260925/_edit_coldjudge.py`, TODO
by `_edit_todo_coldjudge.py` (both refuse a second run). All seven Python
files LF (0 CR) before and after; TODO.md CRLF, 0 bare LF.

## Change

- `local_agent/llama_cpp_client.py`: `_SAMPLER_FIELDS` gains
  `("cache_prompt", bool)`. As with every field there, it reaches the request
  body only when the caller set it; unset callers get the exact old body.
- `local_agent/media_tools.py`: `_run_vision_gpu(..., cache_prompt: bool | None = None)`.
  `None` (every existing caller) leaves the server default, prefix reuse;
  `False` asks for a full cold prefill. The options dict is built once and
  the key added only when a caller decided.
- `local_agent/video_judge.py`: `JUDGE_CACHE_PROMPT = False`, with the 25n
  measurement in the comment, next to the retry constants.
- `local_agent/dspy_orchestrator.py`, `run_qwen_director_scores`: the inner
  `_ask` passes `cache_prompt=video_judge.JUDGE_CACHE_PROMPT` on the first
  attempt and on the 25k retry. Frames, prompts, `num_predict`,
  `repeat_penalty=1.0`, `json_mode` are unchanged.
- Not changed, on purpose: the free-text VLM callers (watcher vision,
  `analyze_video`, `extract_video_actions`) and `dspy_optimizer`'s still /
  video semantic verdicts still run with the server default. They were
  measured (25a/25d) or validated in the warm condition; switching them is
  the same one keyword each, after a measurement.

## Verification that production and the runner now judge the same judge

`_check_v3f_cold.py` → `check_v3f_cold.txt`. The unchanged eval runner
(`gvd_judge_eval.py run --variant production`) on the shipped code, compared
clip by clip with the 25n files that were produced by the measurement-only
`cache_prompt` patch:

| set | clips | raw text identical | checks | scores | prompt eval tokens per request (server log) |
|---|---|---|---|---|---|
| tuning | 50 | **50/50** | 50/50 | 50/50 | 10 479 – 10 660 |
| held-out | 29 | **29/29** | 29/29 | 29/29 | 10 481 – 10 748 |
| phase C | 8 | **8/8** | 8/8 | 8/8 | 10 481 – 10 529 |

Warm runs prefilled ~9 300 of those tokens. And the phase C cold results
are, as 25n §3 I showed, score- and check-identical to the seven live
history rows 262–269: the runner now measures the live judge.

## Re-baseline: warm (v3e, 25l) → cold (**v3f**, shipped)

Reports: `runtime/dspy_opt/judge_eval/report_{v3f,heldout_v3f}.json`,
`phaseC_20260925/report_phaseC_v3f.json`; per-clip diffs
`judge_eval_20260925/compare_v3e_v3f_{tuning,heldout}.txt`. FP = reject
clips that pass, FF = good clips that fail, hc = high-confidence labels.

| set | bar | FP v3e → **v3f** | FF v3e → **v3f** | hc FP | hc FF | partial pass | AUC | distinct triples |
|---|---|---|---|---|---|---|---|---|
| tuning (50) | 0.60 = 0.80 | 7/35 → **8/35** | 0/8 → 0/8 | 3/27 → 4/27 | 0/4 → 0/4 | 6/7 → 6/7 | 0.864 → **0.852** | 25 → 24 |
| held-out (29) | 0.60 | 2/12 → 2/12 | 1/12 → 1/12 | 1/7 → 1/7 | 0/5 → 0/5 | 2/5 → 2/5 | 0.872 → **0.861** | 16 → 16 |
| held-out | 0.80 | 2/12 → 2/12 | 2/12 → **1/12** | 1/7 → 1/7 | 0/5 → 0/5 | 2/5 → 2/5 | | |
| phase C (8) | 0.60 = 0.80 | 1/5 → **0/5** | 1/3 → **0/3** | 0/1 → 0/1 | 0/1 → 0/1 | — | 0.733 → **1.0** | 8 → 8 |

Verdict flips, both bars (all six are the 25n cold-vs-warm differences,
none new):
- tuning: D01 `086a` (reject, late drift) 0.30 → **0.95**, the 25h catch
  was a warm-state catch; B01 `3172` (reject, walls turn green) 0.30 →
  **0.80**; c030 (reject, false pass since 24q) 0.85 → **0.00**, caught.
- held-out: c028 (good) 0.75 → **0.80**, clears the strict bar; the only
  held-out false fail left at either bar is c035 (disputed label, near-black
  cap).
- phase C: D02 `53ae` (good) retried-0.00 → **0.90**, no runaway; D02 `7d15`
  (reject) 0.80 → **0.25**. Both now equal their live rows.

Reject faults still passing at 0.60, v3e → v3f: tuning hard_cut 1/10 →
**0/10**, location_drift 1/4 → 1/4 (c030 out, `086a` in),
color_or_location_drift 0/1 → **1/1** (`3172`), scene_change 0/4 → 0/4,
time_of_day_jump 0/3, black_frames 0/1, wrong_viewpoint 1/3 (D02 `614e`,
unchanged); held-out hard_cut 0/3, location_drift 0/4, black_frames 0/2,
color_or_location_drift 1/1 (c021), all unchanged. Against 24q's warm
baseline v2b (FP 10/35, AUC 0.821; held-out 2/12 / 3/12, AUC 0.809) the
cold judge is still ahead on every rate; against the warm v3c/v3e it is
within one clip per rate, as 25n predicted.

Remaining false passes, cold: tuning D02 `614e`, M04 `15e7`, S01, S05, B01
`93fb`, M04 `cfa7`, D01 `086a`, B01 `3172`; held-out c021, M04 `4c83`.
Remaining false fail: c035. **Compare future judge runs with v3f, not with
v2b–v3e.**

## Tests

- `test_llama_cpp_client.py` +1: `cache_prompt` forwarded as a bool when set
  (False stays False, a truthy value becomes True) and absent when unset.
- `test_media_analysis.py`: the `_run_vision_gpu` options test also asserts
  `cache_prompt` is absent by default and `False` when passed, with
  `repeat_penalty` still 1.08.
- `test_video_judge.py`: `test_judge_vlm_call_sends_repeat_penalty_off` also
  pins `JUDGE_CACHE_PROMPT is False` and the call's `cache_prompt is False`;
  the runaway-retry test asserts both calls are cold.
- `python -m unittest test_llama_cpp_client test_media_analysis test_video_judge test_dspy_orchestrator test_media_accuracy_gate test_generalized_video_director`: 179 OK.
- Full non-live suite on the final files, after the VLM was released:
  **1583 OK (2 skipped)**, 388 s, exit 0 (2026-09-25 12:59:14–13:06:05 local,
  `runtime/dspy_opt/judge_eval/full_suite_20260925_coldjudge.log`); 25l's
  run was 1582, +1 here.

## Housekeeping

- `gvd_vlm_raw.jsonl` 1409 → 1498 (87 judgements plus the pre-existing
  test's one row per unit-test run). `gvd_live_metric_history.jsonl`
  untouched (269 rows).
- `TODO.md` (CRLF): the 25n operator-decision item closed as applied, with
  the v3f baseline numbers; 25o added to the evidence list.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.
- `CHANGELOG/.id_claims/2026-09-25m` remains a stray claim (25l).

## Open

- The other VLM callers still judge warm (see Change). The still and video
  semantic verdicts in `dspy_optimizer.py` gate real renders and return
  structured JSON like the judge; the same keyword would make them
  history-independent too, after a measurement of their own.
- Two rejects the warm judge caught are passed cold: D01 `086a` (late drift
  to pasture; the VLM writes "no birds visible" warm and not cold) and B01
  `3172` (yellow walls turn green). They join the semantic misses (`614e`,
  stylized medium, dry-adult butterflies) rather than the sampling ones.
- The silent server death (24q "cause unknown", four occurrences to date)
  is unchanged; the runner's relaunch handles it, and cold judging means a
  relaunch no longer changes the answers that follow it.
