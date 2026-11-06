# 2026-09-24i — director mock metric and live-metric feedback read `start_prompt`/`video_prompt`

## Why

On 2026-09-16 the Generalized Video Director signature
(`generalized_video_director.director_signature_class`) moved from Wan's
`positive_prompt` to FLUX.1 `start_prompt` + MiniMax I2V `video_prompt`.
Earlier today the mock director LM (`build_mock_lm`) was updated to emit the
new fields. Two readers still only looked at `positive_prompt`:

1. `generalized_video_director.mock_vlm_scores()` scored alignment, motion and
   the Backrooms physics phrase against `positive_prompt`. For a
   current-signature prediction that field is empty, so every candidate got
   alignment 0.05 and temporal 0.42, and mock MIPRO compiles could not tell
   candidates apart.
2. `dspy_orchestrator._fail_result()` wrote
   `"positive_prompt": _field(pred, "positive_prompt")` into the failure
   feedback, so live-metric failure rows carried an empty prompt. The
   success-path feedback in `evaluate_live_candidate` recorded no prompt at all.

`mechanical_director_gate` was checked. It already resolves through
`_director_start_prompt`/`_director_motion_prompt` and reports
`start_prompt is empty` / `video_prompt is empty`, so it needed no change.
Tests were added to lock that in.

## What changed

- `local_agent/generalized_video_director.py` (CRLF preserved):
  - New `_mock_scoring_texts(pred) -> (scene_text, motion_text)`. When either
    `start_prompt` or `video_prompt` is set, the scene text is
    `start_prompt + video_prompt` and the motion text is `video_prompt` alone.
    Otherwise both fall back to legacy `positive_prompt`.
  - `mock_vlm_scores`: intent-token alignment, the `stylized_2d` style lock and
    the Backrooms `yellow`/`backrooms` look bonus read the scene text. Motion
    cues, the length bonus and the Backrooms `handheld walking momentum`
    phrase read the motion text. The local `positive` was renamed to
    `scene_text`. Legacy-only predictions score exactly as before.
- `local_agent/dspy_orchestrator.py`:
  - `_fail_result` feedback: `positive_prompt` key replaced with
    `start_prompt` and `video_prompt`, each resolved through
    `_director_start_prompt(example, pred)` / `_director_motion_prompt(pred)`
    and capped at 500 chars. Those resolvers already fall back to
    `positive_prompt`, so legacy rows still carry their prompt.
  - `evaluate_live_candidate` success feedback now also records the resolved
    `start_prompt` and `video_prompt` (500-char cap).
  - No other code reads a `positive_prompt` key out of the feedback JSON.
    Checked with a scoped grep of `local_agent/*.py`, excluding vendor dirs.

## Tests

- `test_generalized_video_director.MetricTests`: +4
  (`test_current_signature_fields_are_scored`,
  `test_current_signature_candidates_are_distinguishable`,
  `test_motion_cues_come_from_video_prompt_not_start_prompt`,
  `test_backrooms_physics_phrase_read_from_video_prompt`). The existing
  `positive_prompt`-only MetricTests are unchanged and pass through the legacy
  fallback.
- `test_dspy_orchestrator.LiveMetricFlipFlopTests`: +4 (fail row records the
  current fields, fail row falls back to legacy, empty `video_prompt` fail row,
  success row records the current fields).
  `MechanicalGateTests`: +3 (current fields pass without `positive_prompt`,
  `video_prompt is empty` is named, Backrooms camera/motion read from
  `video_prompt`).
- The 8 new metric/feedback tests were run against the pre-change backups and
  all 8 fail there. The 3 gate tests pass on both versions, as expected,
  because the gate was already migrated.
- Full non-live suite from `local_agent`:
  `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')` →
  **Ran 1456 tests, OK (skipped=2)**.
- No ComfyUI, GPU or Ollama process was started.

## Backups

`<file>.bak_predfields_20260924T013821` beside each of
`generalized_video_director.py`, `dspy_orchestrator.py`,
`test_generalized_video_director.py`, `test_dspy_orchestrator.py`.

## Not changed (noted for follow-up)

- `dspy_orchestrator.parse_director_hparams` still iterates
  `HPARAM_FALLBACKS`, which includes `denoise`. The current signature has no
  `denoise`, so every current prediction logs and warns
  `hparam denoise=None missing or unparseable; using fallback 0.9` and gets an
  `hparam_warnings` entry. The value is clamped into `DENOISE_RANGE` (1.0), so
  the only effect is noise.
- `DirectorJSONAdapter.parse` defaults missing `reasoning`/`positive_prompt`/
  `negative_prompt` to `""` but raises `AdapterParseError` for a missing
  `start_prompt`/`video_prompt`. Both end up as 0.02 failures through
  `_fail_penalty`, so scoring is unaffected.
- `build_mock_lm`'s `video_prompt` is the same for every category. The
  Backrooms physics tokens still appear only in its legacy `positive_prompt`,
  so a mock Backrooms candidate now scores temporal ≤ 0.48 under the corrected
  metric.
