# 2026-09-24q — GVD live-metric judge: labeled eval set, fault checks, hard-cut detector

Follows 2026-09-24o (score collapse; false passes on GVD-M03 and GVD-D01).
Existing renders only: no ComfyUI start, no renders. VLM (Qwen2.5-VL Caption V4,
llama.cpp) loaded only after port 8188 closed, all render owners idle, and GPU
≤ 70 °C. The queue owner was held and `check_running_ceiling` checked before
every clip; the VLM was released after every run (peak 72 °C).

Backups: `local_agent/{dspy_orchestrator.py,media_accuracy_gate.py,test_dspy_orchestrator.py}.bak_judgefix_20260924T155503`
(`test_dspy_orchestrator.py` ended up unchanged).

## 1. Measure first: labeled set + runner

- `local_agent/runtime/dspy_opt/judge_eval/gvd_judge_labels.json`: **50 existing
  renders** from `ComfyUI-Shared\output\dspy_opt`, labeled by Claude from 2 fps
  contact sheets plus native-resolution frames for every good/partial
  candidate (sheets in `runtime/dspy_opt/judge_eval_20260924/{sheets,strips}/`).
  **8 good, 7 partial, 35 reject**, each with confidence, fault tags and a
  reason. Labels are against the Beta brief (`user_intent` + `constraints`);
  for the Backrooms batch clips (`gvd_c0xx`) against their rendered prompt pair.
  Partial = no hard fault but a requested action missing; excluded from
  false-pass/false-fail.
- `local_agent/gvd_judge_eval.py`: `run --variant baseline|production`,
  `report`. `baseline` is a verbatim copy of the pre-fix judging block. The
  runner starts the owned llama-server itself with its output logged
  (`results_*.llama_server.log`), retries a clip once on a connection reset,
  and resumes from the results file (`--retry-errors`).

Baseline (pre-fix judge) on the 50 clips, `results_baseline.jsonl`:
- Deterministic: it reproduced the history scores (temperature 0.0, JSON mode).
- Collapse: 13 distinct triples in 50; (0.85, 0.95, 0.90) ×12, (0.95, 0.98, 0.92) ×7.
- @0.60: **false pass 28/35 (80%)**, high-confidence 20/27; false fail 2/8.
- @0.85: false pass 20/35, false fail 5/8.
- **AUC good vs reject 0.414**: a random good clip outscores a random reject
  less than half the time.
- Passed at 0.60: style violations 4/4, wrong viewpoint 3/3, hard cuts 8/10,
  requested subject absent 10/13. Includes text logos ("Deithess" 0.95/0.98/0.90,
  "iye" 0.95/0.98/0.92), a salamander in the creek brief, a clip that opens on a
  studio camera on a tripod, a brown blur with no bee, and three
  instruction-echo renders of abstract glowing shapes (1.0/1.0/0.95).

## 2. Causes found

1. **The judge never saw the brief.** It got only the student's FLUX/MiniMax
   prompts. GVD-M03's MiniMax prompt never mentions water ("pans across the
   moss-covered rocks"), so a waterless clip "matched". The brief's
   constraints ("single skater, no crowd") were never sent, so D04 failed for
   the wrong reason. The echo renders scored 1.0 against their own echoed
   field descriptions.
2. **Anchoring on the prompt text.** The M03 rationale restates the MiniMax
   prompt almost word for word.
3. **Scores before reasoning.** The schema had the three numbers first and the
   rationale after, so the model committed to a default triple first.
4. **Not frame coverage.** `extract_eval_frames(count=3)` is clamped to 8
   uniform frames at 2%..98% (0.16 … 7.84 s for 8 s). The failing late regions
   of D01 (drift from ~5 s) and M03 (cut at 4.7 s) are inside the sample. More
   or re-placed frames were **not** tested.
5. **Not temperature.** Decoding was already 0.0 (only temperature and max_tokens
   reach llama.cpp; `repeat_penalty` is set but not forwarded).

## 3. Fix

- New `local_agent/video_judge.py`:
  - CPU detector over every decoded frame (64×36). A hard cut is a colour-histogram
    step ≥ 0.20, ≥ 8× the local median, grayscale correlation < 0.70, not in
    the first two steps (the I2V conditioning pop), not a flash (the picture
    returns within 12 frames, forward or backward), and not a step into or out
    of a near-black frame. Near-black fraction = frames with mean luma < 16.
    On the set: cuts flagged in D01 `8358` (0.88 s), M03 `371a` (4.71 s),
    D03 `5c73` (1.08 s), D03 `ffd4` (0.92 s); near-black ≥ 25% in 5 rejects;
    **no good or partial clip flagged.** Only 4 of 10 labeled cuts; gradual
    (morph) cuts are left to the VLM. Narrow margin: c017's lights-off frame is
    14.7 luma, M03's post-cut frame 17.2.
  - VLM prompt judged against **BRIEF + CONSTRAINTS** (student prompts no
    longer sent). Order: one line per frame with timestamps, then 7 yes/no
    checks plus `constraint_broken`, then the three scores and rationale.
  - Python caps: subject not visible → alignment ≤ 0.20; medium mismatch
    (only when the brief names a stylized medium) → ≤ 0.30; wrong subject count
    or a real constraint quote → ≤ 0.40; unrequested text/logo → alignment
    ≤ 0.30 and aesthetic ≤ 0.40; location change or cut → temporal ≤ 0.30;
    time-of-day change → ≤ 0.40; detected hard cut → ≤ 0.25; near-black → aesthetic ≤ 0.20.
- `dspy_orchestrator.py`: new `judge_rendered_clip()`; `evaluate_live_candidate`
  uses it (new optional `signals_fn` hook). Output keeps the
  `parse_video_director_scores` shape, so `_fail_penalty`, the curriculum and
  the 0.7·min + 0.3·mean MIPRO scalar are unchanged. Feedback rows add
  `scores_vlm`, `checks`, `caps`, `signals`; `vlm_raw` kept to 4000 chars.
  `run_qwen_director_scores` `num_predict` 1024 → 1536.
- `media_accuracy_gate.py` (CRLF kept): literal-mode override factored into
  `literal_override_block()` and shared by both judges. Old builder output is
  byte-identical in all three modes (verified against the backup).

Two rules were added after the first run (`results_v2a.jsonl`) showed the VLM
misusing checks. Both are general, not per-clip:
(a) `constraint_broken` counts only if the brief has constraints and the text
isn't a dump of check answers; (b) medium mismatch binds only for stylized
briefs (it called clean Backrooms hallways "3D renders"), plus one prompt line
saying a brief that names no medium accepts any realistic look.

## 4. Re-measured on the same 50 clips, final code (`results_v2b.jsonl`)

| | baseline | fixed |
|---|---|---|
| false pass @0.60 | 28/35 (80%) | **10/35 (29%)** |
| … high-confidence labels | 20/27 | **4/27** |
| false fail @0.60 | 2/8 | **0/8** |
| false pass / fail @0.85 | 20/35 / 5/8 | 8/35 / 3/8 |
| AUC good vs reject | 0.414 | **0.821** |
| distinct triples / top share | 13 / 0.24 | 17 / 0.18 |
| hard cuts passed @0.60 | 8/10 | 1/10 |

Still passed: wrong viewpoint 3/3 (drone visible in frame: D02 `614e`,
D01 `3032`; camera operator in shot: c036), late location drift (D01 `086a`,
D01 `3032`, c030), style (S01 photographed print, S05 full colour instead of
B&W ink), M04 dry-adult "teleports" (`15e7`, `cfa7`), B01 wall wobble.
@0.85 the three failed good clips are Backrooms clips at aesthetic 0.80.

Caveats:
- Small set (8 goods), labeled by one reviewer.
- The detector thresholds and rules (a)/(b) were tuned on this same set, so
  these numbers flatter the judge. A held-out set is needed before trusting
  the absolute rates.
- The VLM is prompt-sensitive: between v2a and v2b individual verdicts flipped
  both ways (M05 caught, M04 `15e7` lost).
- Scores are now bimodal (checks fire together: a halo). Collapse is reduced,
  not solved.

The VLM score ranks clips; it does not accept them.

## Runtime notes

- v2a: 4 clips lost to `ConnectionResetError` (llama-server died mid-request and
  the owned-runtime check relaunched it). The same 4 requests replayed with
  server logging (`judge_eval_20260924/repro_vlm_crash.py`,
  `repro_llama_server.log`) all succeeded in ~7 s, about 10.6k tokens, no
  truncation. The media watcher (log idle since 09:57) and the unit tests
  (Comfy `/free` only) were ruled out. **Cause unknown.** The production launch
  sends llama-server output to DEVNULL; the eval runner now logs it. v2b: 0 resets.
- `run_qwen_director_scores` appended 150 rows (3 runs × 50) to
  `runtime/dspy_opt/gvd_vlm_raw.jsonl` (debug dump).
  `gvd_live_metric_history.jsonl` untouched (261 rows).

## Tests

`test_video_judge.py` (25): detector (cut, pan, I2V pop, flash, lights
off/on, black), check parsing, every cap, medium and constraint rules,
orchestrator wiring (brief not student prompt, literal override, legacy
two-arg judge, signals), feedback fields, report maths. Full non-live suite:
**1496 OK (2 skipped)**, was 1471. Run again on the final files, after the
line-ending fix below: 1496 OK (2 skipped)
(`runtime/dspy_opt/judge_eval/full_suite_20260924_final.log`).

Line endings: a scripted `write_text` edit on Windows briefly turned
`dspy_orchestrator.py` (LF) into CRLF on all lines. Caught while diffing
against the backup, and restored to LF. The diff against
`.bak_judgefix_20260924T155503` is now exactly the five intended hunks, with
no edits from other sessions. `media_accuracy_gate.py` is still pure CRLF. The
new files are LF.

## Open

- Future MIPRO scores are not comparable with history rows ≤ 260 (different
  judge, now against the brief).
- Pre-existing, unchanged: a judged clip with all-zero scores gets MIPRO 0.0,
  **below** a render timeout (0.05) or mechanical fail (0.02). The fixed judge
  gives 0.0 more often, so this now matters more. Operator decision.
- Not tried: more or better-placed frames, pairwise first/last-frame questions,
  a separate caption-then-judge call. The biggest remaining misses (viewpoint,
  late drift, stylized medium) look like where those could help.
- Production llama-server output still goes to DEVNULL.
