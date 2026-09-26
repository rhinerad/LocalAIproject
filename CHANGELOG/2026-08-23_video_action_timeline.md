# Video action timeline — 2026-08-23

## Why

Short 5–8 second reference clips need action-level evidence for prompt building.
The previous watcher sent several frames in one request and could return a vague
whole-clip description rather than identifying what changes from second to
second.

## Changed

- `analyze_video` now defaults to `detail: "per_second"`: one exact visual
  observation at every whole second plus the final visible state.
- It then compares every adjacent pair of frames in a separate visual-model
  request, returning a bounded `action_timeline` with visible motion, pose,
  hand/object, camera, and continuity changes. Ambiguous motion must remain
  explicitly uncertain.
- Output now contains `frame_by_frame` and `action_timeline`, both timestamped,
  rather than one undifferentiated visual summary. The result says exactly how
  to use those two evidence streams in a prompt.
- `detail: "half_second"` adds denser coverage; `detail: "overview"` retains
  the prior broad six-frame sampling. Exact `at` values remain supported.
- Frame extraction now decodes through the target timestamp, favoring accurate
  short-clip timing over fast key-frame seeking.
- Motion comparisons now require a visible first-to-second pose/position
  difference for every action verb; an identical adjacent-frame pair is
  deterministically reported as no confirmed change instead of being narrated.
- The tool schema, agent sensory rules, and README describe the new behavior.

## Guardrails retained

No network, model downloads, render starts, audio claims, or evidence-file
changes were introduced. The existing GPU/CPU ownership routing remains in
effect for every vision request; a GPU-reserved render sends vision work to the
CPU tier with `num_gpu: 0` and four CPU threads.

## Verification

- `python -m unittest -v test_media_analysis.MediaAnalysisTests.test_sensory_schemas_are_registered test_media_analysis.MediaAnalysisTests.test_short_video_timeline_covers_each_second_and_the_end_state test_media_analysis.MediaAnalysisTests.test_video_analysis_returns_individual_states_and_motion_beats test_media_analysis.MediaAnalysisTests.test_identical_adjacent_frames_never_claim_motion test_media_analysis.MediaAnalysisTests.test_vision_uses_cpu_when_gpu_is_reserved test_media_analysis.MediaAnalysisTests.test_real_audio_measurement_has_limitations test_media_analysis.MediaAnalysisTests.test_inline_video_prompt_is_found` — 7 passed.
- `python local_agent/test_native_tool_calling.py` — 9 passed.
- `python local_agent/test_router_switching.py` — 13 passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v` — 124/124 valid.
