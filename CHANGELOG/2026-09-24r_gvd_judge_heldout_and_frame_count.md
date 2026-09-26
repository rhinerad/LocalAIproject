# 2026-09-24r — GVD judge: held-out check and frame-count experiment

Follows 2026-09-24q. Operator asked for both a held-out set and a test of
more frames. Existing renders only: no ComfyUI, no renders. The VLM ran under
the same guards as 24q (port 8188 closed, owners idle, GPU ≤ 70 °C at start,
owner held, 82 °C check before every clip, release plus wait for ≤ 58 °C after
each run). Six runs, 0 server crashes, GPU idle afterwards (37 °C).

**Outcome: production stays at 8 uniform frames.** No production code change
in this entry (`dspy_orchestrator.py` untouched).

## Held-out set (labels frozen before any fixed-judge run)

`local_agent/runtime/dspy_opt/judge_eval/gvd_judge_labels_heldout.json`,
sha256 `c915d3adef4dd12b2665a3aaff344a025472030cb676e0058e23f859c88821d9`.
29 clips not used in 24q tuning: **12 good, 12 reject, 5 partial**. Sheets are
in `runtime/dspy_opt/judge_eval_20260924/heldout/`. Excluded as ambiguous, with
reasons in the file: c015, c027, c012 (their prompts ask for, or contradict,
the "fault"), the br_c002/c008/c009 boilerplate prompts, and c031 (a
duplicate).

Bias: every good clip is a Backrooms-batch clip, and 6 of 12 rejects are GVD
Beta clips. Old-judge history scores were visible for the GVD clips while I
scanned; no fixed-judge score was seen before freezing.

## Results (@0.60 unless noted; hc = high-confidence labels only)

| set | judge | false pass | false fail | hc FP | hc FF | FP / FF @0.85 | AUC |
|---|---|---|---|---|---|---|---|
| tuning (50) | baseline | 28/35 | 2/8 | 20/27 | 0/4 | 20/35 / 5/8 | 0.414 |
| tuning | fixed, 8 frames | 10/35 | 0/8 | 4/27 | 0/4 | 8/35 / 3/8 | 0.821 |
| tuning | f12 | 10/35 | 1/8 | 5/27 | 1/4 | 6/35 / 4/8 | 0.809 |
| tuning | f8c | 9/35 | 2/8 | 3/27 | 0/4 | 6/35 / 5/8 | 0.784 |
| **held-out (29)** | baseline | 8/12 | 3/12 | 4/7 | 0/5 | 3/12 / 9/12 | 0.587 |
| **held-out** | **fixed, 8 frames** | **2/12** | **3/12** | 1/7 | 2/5 | 1/12 / 8/12 | **0.809** |
| held-out | f12 | 4/12 | 4/12 | 2/7 | 2/5 | 1/12 / 11/12 | 0.649 |
| held-out | f8c | 4/12 | 4/12 | 3/7 | 2/5 | 1/12 / 11/12 | 0.691 |

- f12 = 12 uniform frames. f8c = 8 uniform frames plus up to 4 frames just
  after the largest colour-histogram steps. Both have the same 12-frame budget.
- On held-out the fixed judge's false-pass reduction holds (8/12 → 2/12, AUC
  0.587 → 0.809). **False fails do not improve (3/12).**
- More frames made things worse on held-out and doubled the time (about 18–20 s
  per clip vs 7–10 s). They also produced 2 parse failures in 158 scorings: the
  output ran away ("no text, no watermark, no people on the cliff edge, …")
  until `num_predict` ran out. The 8-frame judge had 0 in 79.
- Change-placed frames did not rescue late drift. D01 `086a` still scores 0.95
  with extra frames at its largest changes, so the VLM sees the drift but
  does not call it a fault.
- Strict bar: at 0.85, 8 of the 12 good held-out clips fail (Backrooms clips
  sit at aesthetic 0.80–0.85). The later curriculum steps would reject most
  good clips.

## Held-out false fails of the fixed judge (8 frames)

- **c004** (good, high): the requested fluorescent flicker gives one dark frame;
  the VLM answered "different dark hallway" and capped temporal at 0.30.
- **c018** (good, high): CPU cut-detector false positive at 1.83 s. Lights dim to
  luma ~20 (not near-black, so the exposure guard misses it) and come back to
  ~80 within two frames. A before/after layout-correlation rule does not
  separate it: 0.55 vs 0.57 for D01 `8358`'s real cut. **Detector left unchanged.**
- **c035** (good, medium): the prompts contradict each other (FLUX "no body in
  frame"; MiniMax "actor freezes…" and a man is visible), and the requested
  lights-fade trips the near-black aesthetic cap (51% of frames). The label is
  disputed; left as frozen.
- CPU detector on held-out: 2 true cuts (c008 3.33 s, D04 `5ac6` 3.04 s),
  1 false (c018).

## Code (eval tooling only)

- `video_judge.py`: `change_times()` and `extract_frames_at()`, used by the
  f8c eval variant only.
- `gvd_judge_eval.py`: variants `f12` and `f8c`; `--labels` option for both
  `run` and `report`.
- `test_video_judge.py`: +1 test for `change_times`.
- All LF. Full non-live suite **1497 OK (2 skipped)**
  (`runtime/dspy_opt/judge_eval/full_suite_20260924_frames.log`).
- Results: `runtime/dspy_opt/judge_eval/results_{f12,f8c,heldout_baseline,heldout_v2b,heldout_f12,heldout_f8c}.jsonl`,
  log `run_frames_chain.log`. Another 237 debug rows were appended to
  `gvd_vlm_raw.jsonl`; `gvd_live_metric_history.jsonl` untouched (261 rows).

## Open

- The main remaining false-fail mode is requested flicker or lighting change
  read as a location change or cut. It is common in Backrooms prompts.
- The remaining false passes are semantic, not sampling: drone or operator in
  frame, late drift, colour vs ink, dry-adult butterflies.
- `media_tools._run_vision_gpu` sets `repeat_penalty: 1.08` but
  `llama_cpp_client.chat` never sends it (only temperature and max_tokens).
  That likely matters for the runaway outputs above. Not changed: it would
  alter every VLM call in the agent.
- The 0.85 curriculum bar vs the fixed judge's 0.80–0.85 aesthetics on good
  Backrooms clips; and the all-zero score (MIPRO 0.0) ranking below a render
  timeout (0.05) from 24q. Both are operator decisions.
