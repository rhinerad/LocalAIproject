# OPERATOR-APPROVED - 2026-09-02

**BANNER: This is now a real approved calibration INPUT.**

- **approval_id:** `operator-approval-20260902`
- **Operator:** Rhine Duran
- **Date:** 2026-09-02 (America/New_York)
- **Verbatim approval:** "u mark it up. i want this to be a real set"
- **Approved file:** `review-only/turbosparse-mistral-projected-abliteration/approved-calibration-32-pairs.2026-09-02.jsonl` (32 pairs, pa-001..pa-032)
- **SHA-256:** `1F6E4111E17C14CCB5E4DDC0325158ED2780F9A061D31C3957B8B53A632A503A` (11113 bytes)
- **Frozen unapproved draft (do not flip flags):** `draft-calibration-32-pairs.UNAPPROVED.2026-09-01.jsonl`

This approval covers the JSONL as a calibration INPUT only.

## Hard boundary still in force

GPU/predictor work is **not** authorized. Do not start dump, train, convert, bench, registry, ComfyUI, Ollama, or router changes. Do not load a model. Do not modify weights.

Parked checkpoint (do not read weights, do not write):
`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

Do not use the non-`b` tree. Passing the strict validator only marks this file as an approved input. Predictor dump/train remains parked pending a separate GPU gate.

## Validator result

`python tools/powerinfer/validate_approved_calibration_pairs.py` on the approved JSONL:

```json
{
  "pairs": 32,
  "approval_id": "operator-approval-20260902",
  "status": "approved_input"
}
```

`python tools/powerinfer/validate_calibration_pairs.py` on the same file:

```json
{
  "pairs": 32
}
```

`python tools/powerinfer/test_approved_calibration_pairs.py`: Ran 3 tests in 0.015s, OK.

## Frozen evidence (unchanged)

- `draft-calibration-32-pairs.UNAPPROVED.2026-09-01.jsonl` SHA-256 `AB9C774085D7CF744066347ED5989BF91B05624AFE1099A72F6374B7EF41211A`
- `DRAFT-NOT-OPERATOR-APPROVED.md` SHA-256 `FA293E2A631D16EA9F9D269474F60958C16290D0CEE733A03CB96BAD39E9A53C`
- `validation-report.2026-09-01.txt` SHA-256 `72999D665F52D0234600260B30C33E60446B7AFDA900225CEA215A6B93ECDADA`
- `operator-source-safe-subset.UNAPPROVED.jsonl` SHA-256 `3E7C457216F50F594591D86CA50C746D82385B45B22CD727939BCE43568F2E1F`
