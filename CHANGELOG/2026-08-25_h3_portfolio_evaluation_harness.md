# 2026-08-25 — privacy-safe H3 prompt evaluation harness

## Added

- `local_agent/h3_evaluation.py` turns the existing private MiniMax H3 prompt
  corpus check into a versioned, reproducible evaluation report.
- Reports contain only corpus and validator SHA-256 fingerprints, aggregate
  counts, elapsed time, validator error-code counts, and negative-control
  results. They never emit prompt text, names, paths, or media identifiers.
- `local_agent/test_h3_evaluation.py` verifies both aggregation/privacy and
  negative-control behavior.
- A private local report is written to
  `local_agent/runtime/evaluations/h3_prompt_validation_latest.json` when
  requested with `--output`.

## Evidence

Run on 2026-08-25:

```powershell
python local_agent\test_h3_evaluation.py
python local_agent\h3_evaluation.py --dir outputs\equal_shares\prompts_native_r2v --output local_agent\runtime\evaluations\h3_prompt_validation_latest.json
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
```

- Harness regression test: **1/1 passed**.
- Corpus: **124/124 valid** in **1644.92 ms**.
- Synthetic negative controls correctly produced `E01/E02` (wrapper), `E03`
  (missing section), `E10` (zero-based tag), and `E15` (timing bracket).
- Corpus fingerprint: `6868b68d9220aef12f8cf4733060a9d9ec32fac5d3bbfadc79c8eb0e4904776a`.

## Scope

This is an evaluation and evidence layer only. It does not change prompts,
render settings, ComfyUI, model loading, or the paused Equal Shares pipeline.
