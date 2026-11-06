# 2026-09-24l — no spurious `denoise` warning; adapter defaults empty prompts; mock `video_prompt` carries motion

Follow-up to `2026-09-24i`. The 2026-09-16 director signature
(`generalized_video_director.director_signature_class`) emits `start_prompt`,
`video_prompt`, `negative_prompt`, `cfg_scale`, `step_count` — no `denoise`,
no `positive_prompt`.

Backups: `local_agent/{dspy_orchestrator,generalized_video_director,test_dspy_orchestrator,test_generalized_video_director}.py.bak_denoise_signature_20260924T101009`.

No ComfyUI, no GPU, no render. Unit tests only.

## 1. `dspy_orchestrator.parse_director_hparams` — denoise warning

`HPARAM_FALLBACKS` still lists `denoise`, so every current-signature
prediction logged + `warnings.warn()`ed
`hparam denoise=None missing or unparseable; using fallback 0.9` and got an
`hparam_warnings` entry. The value was then clamped to `DENOISE_RANGE`
(1.0, 1.0) anyway.

Change: new `_director_output_fields()` returns the current signature's output
fields (cached; returns `None` if dspy can't be imported). If an hparam is
**absent** (None or blank) **and** the signature doesn't emit it, it takes its
clamped fallback silently. The returned dict still has
`cfg_scale`/`denoise`/`step_count` (`denoise` = 1.0), because callers and
tests read `hparams["denoise"]`. Still warned: garbage in a present field
(e.g. a legacy `denoise="nope"`), missing `cfg_scale`/`step_count`, and
everything when dspy is unavailable (the old behaviour).

## 2. `DirectorJSONAdapter` — missing prompts

The missing-field default set was `{reasoning, positive_prompt,
negative_prompt}`. A student completion without `start_prompt` or
`video_prompt` raised `AdapterParseError`, and the eval recorded a generic
parse failure. **Decision: default both to `""`.** `mechanical_director_gate`
then names the field (`start_prompt is empty` / `video_prompt is empty`,
dspy_orchestrator.py ~611). `_fail_penalty` already matches
`"prompt is empty"` (2026-09-24k), and the GPU path refuses empty prompts
(`start_prompt or video_prompt is empty; skipped GPU`). So an empty default
can't reach a render.
The `denoise` fill in the same adapter was already gated on
`name in signature.output_fields` and is unchanged.

## 3. `generalized_video_director.build_mock_lm._defaults()` — CRLF preserved

`video_prompt` was the same text for every category and had no `_MOTION_CUES`
token. The Backrooms physics phrase was appended only to the legacy
`positive_prompt`. Under the 2026-09-24i metric, mock candidates scored
temporal 0.42 + 0.08 length bonus = 0.50, capped at 0.48 for Backrooms.

Now:
- `video_prompt` = `"Camera tracks forward across one continuous unbroken take, …"`
  (`track` is a motion cue). For Backrooms it also gets
  `"First-person camcorder tracking, handheld walking momentum, realistic camera shake."`
- For Backrooms, `start_prompt` gets the look:
  `"Heavy VHS artifacting, 1990s home video aesthetic, sickly yellow wallpaper, buzzing fluorescent Backrooms corridor."`
- The legacy `positive_prompt` is unchanged (it is only read for pre-2026-09-16 predictions).

Measured over all 16 Beta rows via the mock program + `mock_vlm_scores`:
temporal **0.80** for all 15 drone/macro/stylized rows, **0.96** for the
Backrooms row. It was 0.50 / 0.48.

## Tests

- `test_dspy_orchestrator.py` (CRLF preserved):
  `test_missing_hparams_use_safe_fallbacks` now expects 2 notes, none about
  denoise. New tests:
  `test_current_signature_prediction_does_not_warn_about_denoise` (no notes,
  no warnings, dict shape kept, denoise 1.0),
  `test_legacy_garbage_denoise_still_noted`, and
  `test_json_adapter_defaults_missing_prompts_to_empty` (real dspy
  `DirectorJSONAdapter.parse`, no warnings, then gate names
  `video_prompt is empty`).
- `test_generalized_video_director.py`: new
  `test_mock_video_prompt_carries_motion_and_backrooms_physics` (drone +
  Backrooms temporal ≥ 0.72; Backrooms physics in `video_prompt`, yellow/VHS
  in `start_prompt`, not yellow in `video_prompt`).
- Against the pre-change sources (temp copy), the three behaviour tests fail
  and the Backrooms subtest fails, as expected.
- `python -m unittest test_dspy_orchestrator test_generalized_video_director`:
  46 OK.
- Full non-live suite, run 1: 1460 tests, 1 failure, 2 skipped. The failure
  was `test_tracing.TracingTests.test_concurrency_two_threads` (`6 != 1`), in
  code this change doesn't touch; `python -m unittest test_tracing` passed 3/3
  in isolation. Run 2: same result, same single failure.
- Diagnosis of the `test_tracing` failure: **an existing race, not caused
  by this change.** Evidence:
  - `test_tracing` alone, 6 runs, untouched files: fails once (`.....F`).
  - `test_dspy_orchestrator test_tracing`, 6 runs each: new code `......`,
    pre-change files (temp copy) `......`. One earlier new-code run of the
    same pair failed; a later one passed.
  - Mechanism, from `tracing.py`: `span()` catches a sqlite `DatabaseError`
    while two threads open spans, `_mark_broken()` sets `_BROKEN`, and every
    later span becomes a dummy. The test then counts 1 row instead of 6.
  - Not fixed in this entry; fixed in `2026-09-24n` (WAL first-open race).
- Net for this change: 1460 run = 1456 baseline + 4 new tests. Everything
  passes except the known intermittent tracing race.
