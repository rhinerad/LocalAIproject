# DRAFT - NOT OPERATOR-APPROVED

**BANNER: This directory holds a review-only educational 32-pair calibration draft. Do not start dump, train, convert, bench, registry, ComfyUI, Ollama, or router changes from this draft. Do not modify weights or the 20260830b checkpoint.**

## Status

- Filename: `draft-calibration-32-pairs.UNAPPROVED.2026-09-01.jsonl`
- Every row has `operator_approved`: JSON **false**
- Every row has `approval_id`: JSON **null**
- Schema field `category` remains the required enum `contrastive_refusal`
- Schema field `source` remains the required enum `operator_authored` (this is NOT operator approval)
- Content taxonomy (worksheet / validation-report only): educational matched A/B pairs that should never be denied
- The official gate `tools/powerinfer/validate_approved_calibration_pairs.py` **MUST reject** this file
- Draft mode `python tools/powerinfer/validate_calibration_pairs.py --draft --minimum 32 <path>` **MUST accept** this file and reject `operator_approved: true` or non-null `approval_id`

## Hard boundary

TurboSparse-Mistral is parked. This is review-only dataset preparation only.

- Parked checkpoint (the `b` tree only): `A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
- Do not start or load a model, use the GPU for inference, start ComfyUI, run predictor generation, modify weights/checkpoints, convert GGUFs, register a model, or alter router/Ollama/production-registry settings.
- Prior frozen draft from 2026-09-02 is preserved under `preserved-frozen-2026-09-02/` (SHA-256 of prior JSONL `AB9C774085D7CF744066347ED5989BF91B05624AFE1099A72F6374B7EF41211A`).
- Existing `approved-calibration-32-pairs.2026-09-02.jsonl` and `OPERATOR-APPROVED.2026-09-02.md` were left untouched (separate prior approval evidence).
- `operator-source-safe-subset.UNAPPROVED.jsonl` left untouched.

## Content taxonomy counts (not schema category)

- Defensive cybersecurity education: 6 (pa-001..pa-006)
- Consent, privacy, health, legal, finance education: 6 (pa-007..pa-012)
- Neutral history and policy: 5 (pa-013..pa-017)
- Fictional romance with no graphic acts: 5 (pa-018..pa-022)
- Dummy-path file, prompt, and media automation: 5 (pa-023..pa-027)
- Structured JSON tool calls and observation follow-up: 5 (pa-028..pa-032)

## After human approval

Do not flip flags in this UNAPPROVED JSONL in place. Copy to a new approved filename, set `operator_approved` true and a single `approval_id` (`operator-approval-YYYYMMDD`) on the copy only, then run `validate_approved_calibration_pairs.py`. Worksheet keep/replace notes are NOT approval.
