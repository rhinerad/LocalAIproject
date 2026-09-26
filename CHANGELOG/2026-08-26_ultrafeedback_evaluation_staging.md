# 2026-08-26 — UltraFeedback evaluation staging

## Decision

The dataset review rejected direct live-retrieval ingestion for OpenHermes 2.5,
ScribeAgent, FineWeb-Edu, and The Stack v2. Their broad, random examples would
not improve the local agent's grounded tool behavior. ScribeAgent's production
workflow data is proprietary.

UltraFeedback is useful only as a source of preference-pair candidates for
offline evaluation. It is not a source of current facts or local tool
trajectories, so it must not enter the active Chroma exemplar collections.

## Added

- `local_agent/stage_ultrafeedback_eval.py`
  - Default no-network plan mode.
  - `--execute` is the explicit network/staging gate.
  - Streams `HuggingFaceH4/ultrafeedback_binarized`, `train_prefs`, and uses
    deterministic reservoir sampling to select at most 2,000 records.
  - Writes only provenance-tagged `pending_review` records under
    `local_agent/dataset_eval_staging/pending/`.
  - Does not embed, query Chroma, activate retrieval, start a render, or load a
    model.
- `local_agent/test_stage_ultrafeedback_eval.py` — 3 no-network checks.

## Next gate

Before `--execute`, obtain explicit approval for the Hugging Face download.
After staging, review candidates and convert only useful, anonymized ones into
concrete `operator_eval.py` cases. No automatic promotion is allowed.

## Verification

- `python local_agent/test_stage_ultrafeedback_eval.py` — 3/3 passed.
- `python local_agent/stage_ultrafeedback_eval.py --count 2000` — plan-only,
  no network or model load.
