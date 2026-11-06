# 2026-09-15n - Caption V4 score parser: markdown + regex fallback

Inspection of `logs/run_traces/gvd_run_rows2_20260915T154215*`:
the live MIPRO log/report stored only *parsed* scores (all 0.00). The raw
Caption V4 `analysis` string was never written, so we cannot recover the
judge text from that run. Subsequent evals dump raw analysis to
`local_agent/runtime/dspy_opt/gvd_vlm_raw.jsonl` and `vlm_raw` on feedback.

Parser (`media_accuracy_gate.parse_video_director_scores`):
- Strips ` ```json ` fences anywhere in the reply, not only at the start.
- If JSON is missing, incomplete, or all 0.00, regex-scans axis keywords
  (`alignment`, `temporal`, `aesthetic`, plus full snake_case names) for
  floats / percents. Does not invent scores from unrelated numbers.
- llama.cpp vision calls from the director now set `response_format` JSON
  mode and `num_predict=1024`.

Tests: `tests/test_vlm_score_parser.py` (markdown fence, prose ratings,
JSON-zeros overridden by prose). 35 tests passed with gate suite.
