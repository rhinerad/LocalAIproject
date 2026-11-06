# 2026-08-30 — Approved calibration input gate

## Added

- `tools/powerinfer/CALIBRATION_PROTOCOL.md` documents the difference between
  the eight-row synthetic smoke fixture and an operator-approved research input.
- `validate_approved_calibration_pairs.py` is a strict, stdlib-only gate for
  the next controlled stage. It requires at least 32 unique approved pairs,
  one stable approval ID, the projected-abliteration schema version, and rejects
  obvious paths and secret-like strings.
- `approved_calibration_pairs.template.jsonl` is a deliberately incomplete
  starting template.
- `test_approved_calibration_pairs.py` covers accepted input plus unapproved and
  duplicate-pair rejection.
- `tools/powerinfer/README.md` now links the parked checkpoint gate to this
  protocol rather than leaving the approval requirement implicit.
- `abliterate_turbosparse_v2.py` now calls the strict gate before any full
  checkpoint run. Its explicit `--smoke` path remains available for bounded
  loader/math diagnostics and records that it was not approved input.

## Verification

- Python syntax compilation passed.
- Two validator unit tests passed.
- The checked-in template was intentionally refused because it contains the
  literal placeholder `operator-approval-YYYYMMDD`; this proves the gate fails
  closed rather than treating a template as an approval.
- A full-run probe using the synthetic fixture was refused on its missing
  `pair_id` before CUDA loading or output-directory creation.

## Boundaries retained

No model, GPU, PowerInfer predictor, activation tree, conversion, benchmark,
ComfyUI process, source checkpoint, or existing evidence was changed.
