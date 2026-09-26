# 2026-09-15m - GVD mechanical gate + student LM / hparam fallbacks

Unblocks the Wan → Qwen step after the 2-row live proof (2026-09-15l).

- `mechanical_director_gate` is category-aware:
  - generalized clips: non-empty prompt + positive duration only
  - Backrooms (`category == backrooms` or id `GVD-B*`): at least one camera
    keyword (handheld / camcorder / first-person) and one motion keyword
    (walk / walking / momentum). No exact `handheld walking momentum`.
- Student LM `max_tokens` / Ollama `num_predict` raised to 2048 in
  `harden_student_lm`.
- Missing or unparseable `cfg_scale` / `denoise` / `step_count` warn and
  fall back to 8.0 / 0.35 / 40, then clamp. `DirectorJSONAdapter` fills the
  same defaults so JSONAdapter parse no longer aborts the eval.
- `python -m py_compile local_agent/dspy_orchestrator.py` clean.
  `unittest local_agent.test_dspy_orchestrator` 11 passed.

Live `--run --rows 2` (2026-09-15 15:41–16:20 Eastern, 2323s, exit 0):
- First attempt left Caption V4 on :11436 (optimizer-owned llama-server not
  stopped by `release_after_vlm`). Patched controller to offload that PID.
- Rerun: all four evals reached Wan then Qwen. After VLM, VRAM returned to
  ~700 MiB. Traces in `logs/run_traces/gvd_run_rows2_20260915T154215*`.
- MIPRO still 0.0: Qwen returned 0.00 on all three axes. Hardware path is
  proven; judge JSON quality is the next software issue.
