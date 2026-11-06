# 2026-09-25a — free-text VLM callers measured at repeat_penalty 1.0 vs 1.08; action extractor pinned to 1.0

Follows 2026-09-24ae, which made `repeat_penalty` actually reach llama-server
and left the free-text callers running at the intended 1.08 "unmeasured
beyond the probe". The operator asked for the same measurement the judge got.
There is no labeled set for these callers, so this is an A/B on the same
inputs: every output at 1.0 (what the callers ran at until 24ae) and at 1.08
(what they run at now), compared for truncation, format compliance,
repetition and required-field presence, with a repeat run at 1.0 as the
determinism control.

VLM only, one owned llama-server launch under `gvd_judge_eval.preflight`
(8188 closed, owners idle, GPU 29 °C at start, 82 °C check before every call,
release and cool-down after). 75 calls, 0 errors, server alive throughout,
GPU 35 °C afterwards. No ComfyUI, no renders.

Harness and data: `local_agent/runtime/dspy_opt/judge_eval_20260924/freetext_penalty_ab.py`,
rows `freetext_penalty_ab.jsonl` (full texts), `freetext_penalty_ab_summary.json`,
log `freetext_penalty_ab_run.log`, server log `freetext_ab_llama_server.log`.

## Inputs

8 labeled clips (c005, c017, D03 `1adb`, M01 `4f74`, S05 `361f`, D01 `6609`,
M04 `15e7`, c036: Backrooms hallways, drone, macro, stylized, black/logo,
butterfly, operator-in-frame). Per clip, the exact prompt builders production
uses:

| caller | production path | frames | budget |
|---|---|---|---|
| `see_image` | watcher vision job, default `_build_prompt` | 1 (judge frame 4) | 512 |
| `tl_observe` | `analyze_video` → `_timeline_observation_instruction` | 1 | 512 |
| `tl_change` | `analyze_video` → `_timeline_change_instruction` | 2 | 512 |
| `actions` | `extract_video_actions` → `_action_frame_instruction` (ffmpeg `fps=2,scale=768:-1`) | 16–20 | 2048 |
| `actions_h3` | same, `format_h3_beats=True` (3 clips) | 16–20 | 2048 |

## Results

Mechanically, nothing broke at either value: **0 of 35 outputs truncated at
max_tokens** at 1.0 and 0 of 35 at 1.08; every action log labelled every
requested frame (coverage complete 11/11 both ways) and every line matched
`Frame N | t=… | …` (0 non-conforming of 196, both ways); no run of identical
lines; no audio claims.

| caller | mean tokens 1.0 → 1.08 | top repeated 4-gram (mean) | distinct-word ratio | text identical | similarity |
|---|---|---|---|---|---|
| see_image (8) | 171 → 185 | 1.5 → 1.5 | 0.64 → 0.67 | 0/8 | 0.23 |
| tl_observe (8) | 141 → 160 | 1.6 → 1.3 | 0.56 → 0.66 | 0/8 | 0.43 |
| tl_change (8) | 39 → 50 | 0.9 → 0.9 | 0.71 → 0.68 | 4/8 | 0.69 |
| actions (8) | 818 → 744 | 16.8 → 11.4 | 0.14 → 0.18 | 0/8 | 0.41 |
| actions_h3 (3) | 716 → 626 | 18.0 → 13.3 | 0.15 → 0.21 | 0/3 | 0.52 |

Prose callers: different wording, same structure, slightly more hedging
words at 1.08 (`unknown` 4 → 7 in `tl_observe`, `no confirmed change` 23 →
28 in `tl_change`), which is the direction the instructions ask for. Nothing
in the metrics or a read of the pairs (e.g. M01 web caption, `jsonl`) says
1.08 is worse; nothing says it is better either.

Action logs: repetition is lower at 1.08, but the required per-line fields
get rarer. Lines carrying a camera-motion term (`static`, `push-in`, …,
`camera`): **72/140 (51%) at 1.0 → 26/140 (19%) at 1.08**; H3-beat variant
16/56 → 0/56. The word `static` alone: 68 → 6. D03 at 1.08 is genuinely more
specific ("leans further into the left curve") but drops "Camera is static"
from 14 of 16 lines; c005 at 1.08 writes "No visible change in empty yellow
hallway" 19 times and states the camera on none. Same mechanism as the judge
in 24ae: a field that must repeat on every line is exactly what a repeat
penalty makes cheaper to omit.

Caveats, stated plainly:
- The 16–20-frame batch call is **not deterministic** at temperature 0: the
  1.0 control repeat of c005 `actions` differed from its first run
  (similarity 0.891, first line already differs) and had 0/20 camera lines
  where the first run had 20/20. The single-frame and two-frame calls were
  identical on repeat (4/4). So the camera-field figure is noisy and
  all-or-nothing per clip (1.0: 4 of 8 clips 100%, 4 clips 0%; 1.08: 1 of
  8). n = 8 clips. The direction is consistent with the mechanism; the size
  is not well measured.
- The 1.08 call always ran second on the same images, so its lower wall
  time (actions 14.1 s → 7.5 s) is the prompt cache, not the penalty.
- No labels: this measures form, not truth. Whether a caption at 1.08 is
  more or less *accurate* was not judged.

## Decision

- `extract_video_actions` (`media_tools.py`, LF): its `_run_vision_gpu` call
  now passes `repeat_penalty=1.0`, with the measurement in a comment. Its
  output is a fixed per-line format with required repeated fields, the same
  class as the judge's checklist; the penalty showed no mechanical benefit
  for it (no truncation to prevent) and a field-loss signal against it; and
  1.0 is the value it was validated at. Backup
  `media_tools.py.bak_actions_rp_20260925T003000`.
- `see_image` / watcher vision jobs and `analyze_video`'s timeline calls
  stay at 1.08 (the `_run_vision_gpu` default): prose output, no regression
  measured, marginally more conservative wording.
- The camera-motion field being absent on half of all action-log lines
  **at 1.0** is a pre-existing prompt-compliance problem, not a penalty
  problem; noted as open.

## Tests

- `test_media_analysis.py` `test_action_job_uses_watcher_owned_runtime_after_it_consumes_vram` now captures the `_run_vision_gpu` kwargs and asserts `repeat_penalty == 1.0` and `num_ctx == 32768` (backup `test_media_analysis.py.bak_actions_rp_20260925T003000`); module 22 OK. The existing 1.08-default assertion for `_run_vision_gpu` still holds.
- Full non-live suite: **1535 OK (2 skipped)**, 284 s, exit 0 (2026-09-25 00:3x local, `runtime/dspy_opt/judge_eval/full_suite_20260925_actions_rp.log`); same count as 24ae, no test added, one extended.

## Housekeeping

- `TODO.md` "GVD live-metric judge — operator decisions closed" section: the
  "watch the free-text VLM callers" item closed with this measurement; one
  new open item for the camera-motion field compliance.
- `HANDOFF_STATUS.md` regenerated with `python scripts/write_handoff_status.py`.

## Open

- Action-log camera-motion field present on only ~half of lines at 1.0 and
  nondeterministic per clip on a 20-frame batch; a prompt fix (e.g. a
  mandatory `cam=` slot in the line template) plus a compliance check in
  `_action_coverage` would be the way to make it reliable. Not a sampler
  issue.
- 20-frame batch calls are not bit-deterministic at temperature 0 on this
  server build (flash-attn/batched decode); single-frame calls are. Matters
  for any future A/B on `extract_video_actions`: repeat the control.
- Another 75 rows of texts sit in `freetext_penalty_ab.jsonl`; nothing was
  appended to `gvd_vlm_raw.jsonl` (`_run_vision_gpu` does not dump).
