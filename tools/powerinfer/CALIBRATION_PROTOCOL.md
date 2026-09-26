# Projected Abliteration calibration protocol

## Status and boundary

The existing `calibration_pairs.synthetic.jsonl` is a loader/math smoke fixture.
It is **not** an approved calibration set and must never unlock predictor
generation, conversion, benchmarking, or production registration.

The acceptance gate is `validate_approved_calibration_pairs.py`. It does not
judge whether an edit is scientifically effective; it verifies that a human has
explicitly approved a traceable, non-private calibration set before GPU work is
allowed to begin.

## JSONL record schema

Each non-empty line must be one JSON object with:

```json
{
  "pair_id": "pa-001",
  "harmful": "<operator-approved contrastive prompt>",
  "harmless": "<matched harmless contrastive prompt>",
  "category": "contrastive_refusal",
  "source": "operator_authored",
  "approval_id": "operator-approval-YYYYMMDD",
  "operator_approved": true,
  "schema_version": "projected-abliteration-v1"
}
```

Required rules:

- Supply at least 32 unique pairs. Eight is adequate only for a loader smoke
  test, not a calibration gate.
- Both prompts must be short, matched contrastive inputs. Never use private
  chats, local paths, API keys, credentials, personal identifiers, or raw media
  descriptions.
- `pair_id` values must be unique and stable for auditability.
- `approval_id` must identify the operator decision that approved the entire
  set. It is an audit label, not an authentication secret.
- Keep a copy of the validated file next to the resulting checkpoint. Do not
  overwrite prior calibration evidence.

## Required sequence after validation

1. Run the strict validator against the operator-approved JSONL.
2. Use a fresh immutable output directory for the projected edit.
3. Regenerate predictors and activations from that exact edited checkpoint.
4. Run mechanical, base-completion coherence, sparsity, and throughput checks.
5. Require human review before production registry registration.

Passing this validator does not make a model accepted. It only authorizes the
next controlled research stage.
