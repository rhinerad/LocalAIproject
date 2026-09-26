# 2026-08-30 — TurboSparse calibration boundary

Added `calibration_pairs.template.jsonl` and
`validate_calibration_pairs.py`. The validator checks JSONL structure, minimum
pair count, and rejects obvious path/secret leakage without loading a model.
The template is intentionally not used for abliteration: placeholder strings
are not valid representation evidence. A real run requires operator-approved,
benign contrastive pairs, followed by fresh PowerInfer profiling and quality
validation.
