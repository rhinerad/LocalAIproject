# 2026-09-24o — director label echo fixed; director recompile started

Follows 2026-09-24k. Operator asked: fix the label echo and the denoise
warning, then recompile.

Backups: `*.bak_labelecho_20260924T105305` (`dspy_orchestrator.py`,
`generalized_video_director.py`, both test files).

## Denoise warning — already fixed by 2026-09-24i

`parse_director_hparams` no longer notes/warns for an hparam the signature
does not emit. Verified with warnings-as-errors: a correct prediction returns
`denoise 1.0` and no notes; garbage `cfg_scale` still warns. Nothing added.

## Label echo

Measured with the live student (`qwen2.5:1.5b`) before the fix: prompts began
"FLUX.1 T2I:", "MiniMax I2V:", "Start frame:", "Video prompt:", bare
"FLUX.1 …"; one GVD-D01 `start_prompt` was the OutputField description
verbatim ("FLUX.1 still prompt: descriptive lighting/texture/composition for
the opening frame only").

- `generalized_video_director.py` (CRLF kept): instructions no longer use the
  `start_prompt (FLUX.1 T2I): …` line shape and say never to prefix a label;
  `start_prompt`/`video_prompt` OutputField descs reworded so they do not read
  as prompt text.
- `dspy_orchestrator.py`:
  - `strip_prompt_label()` in `_director_start_prompt`/`_director_motion_prompt`
    (every render path resolves through these): removes leading
    field/model labels ending in ":" and bare versioned tokens "FLUX.1 ",
    "MiniMax I2V/T2I/H3 ". Leaves "Flux capacitor…", "MiniMax-style…".
  - `instruction_echo()`: 6-word-shingle overlap with the live instructions +
    field descs. `evaluate_live_candidate` fails such a candidate **before the
    GPU** (`mechanical: instruction echo …`, penalty 0.02);
    `mechanical_director_gate` names the field. False-positive scan: **0 of
    263** unique real prompts (Backrooms 24-clip pack + FLUX/MiniMax text
    embedded in the 144 renders on disk).
- Found while probing, fixed (pre-existing): `DirectorJSONAdapter.parse`
  checked `_try_parse_float` but then validated the **raw** value, so
  `{"cfg_scale": {"value": "4.0"}}` or `"24-32"` raised a pydantic
  ValidationError (a zero-score trial during compile). It now stores the
  coerced float. Also unwraps an object-valued text field
  (`{"description": "…"}`) seen once on GVD-B01; not reproduced in 3 later
  samples, so covered by unit test only.

After, live student on 8 Beta rows: labelled 0, echo 0, exceptions 0.
Tests: 12 new; full non-live suite **1471 OK (2 skipped)**.

## Recompile — in progress

`local_agent/_recompile_gvd_director_20260924.py`, detached PID 52756, started
11:04. Settings = `dspy_orchestrator.py --compile` defaults (16 rows, 1 trial,
1 candidate, 0 demos). Previous artifact backed up as
`models/dspy_compiled/generalized_video_director_mipro.json.bak_recompile_20260924T110411`;
`…_path_b_20260917T004757.json` untouched.

Backend: sanctioned `restart_comfy_rockernow.ps1` (Rockernow PID 57888),
stopped at the end. Queue owner held; `thermal_guard.wait_before_render` and
`wait_after_render` around every render; 82 °C / 3-telemetry-failure watchdog
→ `/interrupt`; `XAI_API_KEY` removed so the proposer stays local
(`llama3.1:8b`). Metric rows go to `gvd_live_metric_history.jsonl`.

First render verified from its embedded workflow
(`ComfyUI-Shared\output\dspy_opt\gvd_GVD-D01_8358737ce0_00001_.mp4`): no label
in FLUX or MiniMax text, KSampler denoise 1.0 / 24 steps, MiniMax node 35
**20** steps. 1031 s, peak 77 °C, VLM 0.865.

Expected: ~18.6 min/row, 16-row baseline + 16-row trial ≈ 10 h → about
21:00–21:30 today. Progress: `local_agent/runtime/dspy_opt/recompile_20260924/status.json`
and `run.out.log`. Not verified until the saved artifact's instructions are
checked and its renders reviewed; the VLM score is a ranking, not acceptance.

## Recompile outcome (15:26) — stopped after pass 1, program saved directly

MIPRO ran the baseline evaluation **plus** 1 trial (log: "Trial 2 / 1"), i.e.
two 16-row passes. The single instruction candidate was the restored original,
verbatim, so pass 2 could not change the saved program. Operator chose to stop.

- Pass 1: 16/16 rendered, 0 render errors, no watchdog trip, peak 77 °C,
  ~15.4 min/row. **Default program score 82.93.** Rows are in
  `gvd_live_metric_history.jsonl` (rows 245–260).
- Stop: compile PID 52756 killed; in-flight pass-2 GVD-D01 interrupted
  (`/queue` clear + `/interrupt`); Rockernow PID 57888 stopped via the
  Rockernow-only check; queue owner released; GPU 47 °C / 54 MiB after.
- `models/dspy_compiled/generalized_video_director_mipro.json` written from
  `gvd.build_director_program().save()` — what `compile_director` would have
  saved (0 demos, 1 candidate = original). Instructions ==
  `DIRECTOR_SIGNATURE_INSTRUCTIONS` (1490 chars; the 09-17 file had 75);
  survives `load()`. 09-17 file kept as `.bak_recompile_20260924T110411`.
  `…_path_b_20260917T004757.json` still carries the 75-char docstring;
  nothing loads it.

VLM judge caveat: numeric scores collapse to default triples — (0.85, 0.95,
0.90) on 7/16 rows and (0.95, 0.98, 0.92) on 4/16 — while rationales are
clip-specific. Same pattern in older history. With one candidate this did not
affect what was saved; any future multi-candidate compile would depend on it.

Visual review (2 fps sheets, `local_agent/runtime/dspy_opt/recompile_20260924/review/`;
sheet-level ranking only):
- D03 0.929 — one rider, rooster tail, consistent canyon; plausible keep.
- D04 0.325 FAIL — correct fail, wrong reason: blue hour → night + moon, and
  2–3 extra people (constraints: single skater, no crowd). Reject.
- M03 0.865 pass — **false pass**: no creek/water/caustics; hard cut at ~4.5 s
  to a different rock. Reject.
- B01 0.74 pass — right look, continuous handheld walk; walls lean/wobble and
  door frames shift. Needs native-frame review.
With the morning's D01 verify render: 2 false passes of 5 reviewed.
