# 2026-09-24ae — llama.cpp client forwards repeat_penalty; the checklist judge keeps it off (measured)

Follows 2026-09-24r, which found that `media_tools._run_vision_gpu` sets
`repeat_penalty: 1.08` but `llama_cpp_client.chat` only ever sent
`temperature` and `max_tokens`, so every VLM call in the agent has run with
the penalty effectively off (1.0) since the llama.cpp runtime was adopted.
24r left it alone because it would alter every VLM call; the operator asked
for it to be fixed. The plumbing is fixed. The effect on the GVD judge was
then **measured**, and it is bad enough that the judge now pins the penalty
off explicitly; free-text callers get the intended 1.08.

VLM only, under the usual guards (`gvd_judge_eval.preflight`: port 8188
closed, owners idle, GPU ≤ 70 °C at start; owner held; 82 °C check before
every clip; release and cool-down after each run). Four llama-server
launches, 0 crashes, 0 connection resets, GPU 37 °C afterwards. No ComfyUI,
no renders.

Backups: `local_agent/{llama_cpp_client.py,media_tools.py,dspy_orchestrator.py,dspy_optimizer.py,test_video_judge.py}.bak_repeatpenalty_20260924T223830`.

## 1. The fix (`llama_cpp_client.py`, LF)

`_SAMPLER_FIELDS` = repeat_penalty, repeat_last_n, presence_penalty,
frequency_penalty, top_k, top_p, min_p, seed, stop. Each is copied into the
`/v1/chat/completions` body, cast, **only when the caller set it**; nothing
is invented, and callers that set none get the exact old body. llama-server
(build 10516, `--repeat-penalty` in `--help`) copies unknown OpenAI-body
fields through to its native sampler params.

Confirmed live (`runtime/dspy_opt/judge_eval_20260924/probe_repeat_penalty.py`,
result `probe_repeat_penalty_result.json`, text-only, same launch args as
production): `/completion` echoes `generation_settings.repeat_penalty = 1.08`;
through `llama_cpp_client.chat` at temperature 0, "write yes 40 times" gives
120 "yes" tokens at 1.0, 60 at 1.08 and 58 (with case drift) at 1.5. The
field is honoured on the endpoint the agent uses.

New `test_llama_cpp_client.py` (5): forwarding, Ollama-only keys never
reach the body, unset fields not invented, casts, image data URLs.

## 2. Measured on the judge: 1.08 forwarded (`results_v2c.jsonl`, `results_heldout_v2c.jsonl`)

Same 50 + 29 labeled clips, same judge code as 24ac, only difference: the
penalty now reaches the server. 45/50 and 29/29 clips changed at least one
score.

| set | bar | FP (1.0 → 1.08) | FF (1.0 → 1.08) | hc FP | hc FF | AUC | parse failures |
|---|---|---|---|---|---|---|---|
| tuning (50) | 0.60 | 10/35 → **4/35** | 0/8 → **2/8** | 4/27 → 1/27 | 0/4 → 1/4 | 0.821 → 0.875 | 0 → **2** |
| tuning | 0.80 | 10/35 → 4/35 | 0/8 → 2/8 | 4/27 → 1/27 | 0/4 → 1/4 | | |
| held-out (29) | 0.60 | 2/12 → **0/12** | 3/12 → **6/12** | 1/7 → 0/7 | 2/5 → 3/5 | 0.809 → 0.812 | 0 → **1** |
| held-out | 0.80 | 2/12 → 0/12 | 3/12 → **7/12** | 1/7 → 0/7 | 2/5 → 3/5 | | |

Reports: `report_v2c.json`, `report_heldout_v2c.json`. Per-clip: 10 verdict
flips on tuning (8 rejects/partials caught, 2 goods lost), 6–8 on held-out
(2 rejects caught, 3–4 goods lost, 1 partial regained). ~8 s per clip both
ways.

Why it is not simply "stricter": the mechanism is token frequency, not
evidence.
- The output is a fixed checklist of seven yes/no answers. After several
  "yes" tokens the penalty makes "yes" more expensive and "no" cheaper. The
  goods lost are Backrooms hallway walks now answered
  `same_place_in_all_frames: no` with rationales such as "a different place
  (empty hallway) compared to the BRIEF's backroom scene" (c016) or "change
  in lighting and door position, indicating movement through the hallway"
  (c017, movement is the brief). c038 was answered "abrupt cut" with the CPU
  detector reporting none; c025 "requested subject not visible" for a
  hallway that is visible in every frame.
- Several rejects are "caught" for the wrong reason: `constraint_broken` is
  now filled with the CONSTRAINTS line quoted verbatim (D02 `614e`, S05, D01
  `086a`/`3032`), which rule (a) from 24q accepts because it is not a dump
  of check answers. Right verdict, ungrounded evidence.
- **3 of 79 outputs close the JSON object right after the checks**, before
  the three scores, and fail parsing (`missing or invalid float score`).
  0 of 79 did at 1.0. In production that is a `_fail_result` (0.01), not a
  judged clip. This is the opposite of the runaway that 24r hoped the
  penalty would curb; no runaway occurred at 8 frames in either run.

The false-pass reduction is real but comes from a bias that also fails good
clips and breaks the schema. The judge stays at the behaviour validated in
24q/24r/24ac.

## 3. Production state after this entry

- `media_tools._run_vision_gpu(..., repeat_penalty=1.08)`: new parameter,
  default unchanged, **now live** for free-text callers: `_vision_direct`,
  the media watcher's queued vision jobs, `extract_video_actions` batches,
  the caption/lifecycle diagnostics. These run at 1.08 for the first time;
  their output is prose or beat lists, where a mild anti-loop penalty is what
  the value was written for. Unmeasured beyond the probe.
- `dspy_orchestrator.run_qwen_director_scores`: `repeat_penalty=1.0`,
  with the measurement in a comment. `test_video_judge.py` +1 asserts it.
- `dspy_optimizer.py` (CRLF/LF mix preserved: +4 CRLF lines, LF count
  unchanged): the still semantic verdict, its FORMAT RETRY, and the video
  semantic verdict pass `repeat_penalty=1.0`. They return a structured JSON
  verdict (they even have a JSON-format retry path), were validated with the
  penalty effectively off, and gate real renders; not changed unmeasured.
- `gvd_qa/caption_v4.py` sets no penalty and is unchanged (stays 1.0).
- Switching the judge to 1.08 later is one keyword argument; `results_v2c`
  is what that produces.

## 4. Verification that the judge is unchanged at explicit 1.0

`results_v2d_check.jsonl` / `results_heldout_v2d_check.jsonl`: the 13
clips that flipped or failed to parse in v2c, re-judged with the final code
(penalty sent as 1.0). **All 13 identical to v2b** in scores, checks and parse status (`run_v2d_check_chain.log`), including the three that failed to parse at 1.08. Sending `repeat_penalty: 1.0` is byte-for-byte the disabled sampler, and the judge is deterministic at temperature 0, as 24q found.

## Tests

- `test_llama_cpp_client` (5, new), `test_media_analysis` (22, the existing
  1.08 assertion still holds), `test_video_judge` (27, +1): OK.
- Full non-live suite on the client change alone: 1534 OK (2 skipped)
  (`full_suite_20260924_repeatpenalty.log`; other sessions added tests since
  24ad's 1529).
- Full non-live suite on the final files: **1535 OK (2 skipped)**, 246 s, exit 0 (2026-09-24 23:35–23:40 local, run after the last edit, the FORMAT RETRY pin; the chain's earlier run on all but that line was also 1535 OK)
  (`full_suite_20260924_repeatpenalty_final2.log`; the chain's run is in `run_v2d_check_chain.log`).

## Housekeeping

- `TODO.md`: new section "GVD live-metric judge — operator decisions closed —
  2026-09-24ac/ad/ae" at the top of the queue (below the 2026-09-22j START
  OVER banner): the three decisions closed as `[x]`, four follow-ups open.
  Backup `TODO.md.bak_gvd_judge_20260924T234500`.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`
  (generated file, not hand-edited).

## Open

- Free-text VLM callers now run at 1.08 without a labeled measurement. If
  captions or action beats change character, `repeat_penalty` in
  `_run_vision_gpu` is the knob; 1.0 restores the pre-24ae behaviour exactly.
- The judge's remaining misses (viewpoint, late drift, stylized medium) are
  unchanged; a sampler penalty is not the tool for them.
- Another 79 + 13 debug rows appended to `gvd_vlm_raw.jsonl`;
  `gvd_live_metric_history.jsonl` untouched (261 rows).
