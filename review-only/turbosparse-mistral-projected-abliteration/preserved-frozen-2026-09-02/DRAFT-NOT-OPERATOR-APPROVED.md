# DRAFT - NOT OPERATOR-APPROVED

**BANNER: This directory is review-only. Do not start dump, train, convert, bench, registry, ComfyUI, Ollama, or router changes from this draft. Do not modify weights or the 20260830b checkpoint.**

## Status

This isolated directory holds a review-only 32-pair calibration draft for projected abliteration.

- `operator_approved` is JSON `false` on every row.
- `approval_id` is JSON `null` on every row.
- Schema field `source` is exactly `operator_authored` (required enum). The draft banner states these pairs are **NOT** operator-approved yet.
- The official gate `tools/powerinfer/validate_approved_calibration_pairs.py` **MUST reject** this file. That rejection is success for this stage.

## Hard boundary

TurboSparse-Mistral is parked. This is review-only dataset preparation.

- Parked checkpoint (the `b` tree only): `A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
- Do not start or load a model, use the GPU for compute, start ComfyUI, run predictor generation, modify weights/checkpoints, convert GGUFs, register a model, or alter router/Ollama/production-registry settings.
- Do not overwrite evidence. Do not delete existing files.
- Existing `operator-source-safe-subset.UNAPPROVED.jsonl` was left untouched (label list only: `["1A.","1B.",...,"32B."]` with no prompt bodies).
- No CHANGELOG entry was written because the operator asked for this isolated directory only.

## Provenance of pair bodies

- **pa-001..pa-008:** copied from `tools/powerinfer/calibration_pairs.synthetic.jsonl` (the only persisted pair bodies in-repo). JSON uses straight ASCII apostrophes (`can't`, not curly).
- **pa-009..pa-032:** drafted in the same one-line contrastive-refusal contract so the file meets the 32-pair count. They are NOT copied from private chats. They are NOT operator-approved. The originating operator message said pairs were "provided" but those bodies were not persisted on disk.

## Protocol citations

- `tools/powerinfer/CALIBRATION_PROTOCOL.md`
- `tools/powerinfer/validate_approved_calibration_pairs.py`
- `tools/powerinfer/README.md` (TurboSparse section)
- `work/POWERINFER_STATUS_2026-08-30.md`
- `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`

## After human approval

Copy to a new approved filename; do not flip flags in the UNAPPROVED JSONL in place. Then run `python tools\powerinfer\validate_approved_calibration_pairs.py` on the new approved copy.
