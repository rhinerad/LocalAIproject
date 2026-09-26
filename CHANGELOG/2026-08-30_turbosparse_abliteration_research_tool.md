# 2026-08-30 — TurboSparse abliteration research tool

Added `tools/powerinfer/abliterate_turbosparse.py` as an opt-in, no-download
research utility for the exact Tiiny TurboSparse-Mistral/Mixtral custom
checkpoints. It validates a ReLU-family architecture, measures a bounded
refusal direction with a 4-bit GPU copy, applies an allowlisted projection to
`o_proj`/`down_proj` in a full-precision CPU copy, and writes a staging
directory with hashes and calibration provenance.

The script does not alter source weights or claim that abliteration preserves
quality. Any output must be profiled again because PowerInfer predictors and
activation statistics are tied to the exact edited weights. No model was loaded
or GPU work was started by this documentation change.
