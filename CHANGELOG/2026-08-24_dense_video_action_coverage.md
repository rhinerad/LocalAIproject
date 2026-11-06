# Dense video-action coverage — 2026-08-24

## Why

For 5–8 second reference clips, a frame sampler alone was not enough: the VLM
could collapse several observations into a vague whole-clip summary. That made
it too easy for prompt building to assume an unlabelled second contained a
particular action.

## Changed

- `extract_video_actions` now builds a deterministic ordered table of every
  extracted frame's evidence window and sends that table with the matching
  sequential images to the lazy Qwen2.5-VL runtime.
- The VLM instruction requires exactly one `Frame N | t=...` line per supplied
  image, including pose, position, hand/object contact, facing, visible motion,
  camera state, and an explicit `no visible change` or `uncertain` where
  appropriate.
- The result now preserves `observation_windows` and a `coverage` report. A
  frame label omitted by the VLM is returned as a missing evidence window; the
  agent never synthesizes a replacement action.
- `fps` is now exposed in the native tool schema. Its default remains 1 FPS;
  2 FPS is available only for genuinely action-critical half-second changes.
- The optional H3 source-note form no longer asks for bracketed timing blocks,
  because those are not native MiniMax H3 grammar.

## Guardrails retained

No model is loaded for ordinary chat. The existing watcher still owns VLM
startup/release and defers video jobs behind ComfyUI renders. No render, media
upload, manifest, or evidence file is changed; temporary sampled frames remain
the only cleaned artifacts.

## Verification

- `python -m unittest local_agent.test_media_analysis` — 19 passed.
- `python -m unittest local_agent.test_media_gpu_queue` — 18 passed.
- `python -m unittest discover -s local_agent -p 'test_*.py'` — 115 passed.
- `python local_agent/agentic_eval.py` — 5/5 passed with mocked calls; no model
  or render was started.
- `python local_agent/validate_h3_prompt.py --dir
  outputs/equal_shares/prompts_native_r2v` — 124/124 valid.
