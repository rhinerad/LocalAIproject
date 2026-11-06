# PowerInfer STATUS (pointer)

Canonical long-form status remains `work/POWERINFER_STATUS_2026-08-30.md` and
`tools/powerinfer/README.md`. This file exists so agents that look for
`tools/powerinfer/STATUS.md` find the same parked boundary.

## 2026-09-08e — prompt-pack evidence finish-prove (cross-ref only)

Prompt-pack QA finish-prove landed; PowerInfer untouched. See
CHANGELOG/2026-09-08e_prompt_pack_evidence_finish_prove.md. TurboSparse still parked.

## 2026-09-08 — educational review-only draft (UNAPPROVED)

- Deliverable dir: `review-only/turbosparse-mistral-projected-abliteration/`
- Required draft files present:
  - `draft-calibration-32-pairs.UNAPPROVED.2026-09-01.jsonl` (32 pairs; all `operator_approved: false`; all `approval_id: null`)
  - `reviewer-worksheet.md` (keep/replace notes are NOT approval)
  - `DRAFT-NOT-OPERATOR-APPROVED.md`
  - `validation-report.2026-09-01.txt`
- Content taxonomy counts: 6/6/5/5/5/5
  (defensive cyber / consent-privacy-health-legal-finance / history-policy /
  fictional romance / dummy-path automation / JSON tool-call follow-up)
- Draft validator: `python tools/powerinfer/validate_calibration_pairs.py --draft --minimum 32 <jsonl>` PASS
- Approved gate: `validate_approved_calibration_pairs.py` MUST reject (and does)
- Prior frozen crime/refusal draft preserved under `preserved-frozen-2026-09-02/`
- Prior approved INPUT `approved-calibration-32-pairs.2026-09-02.jsonl` left untouched
- TurboSparse-Mistral remains **parked**. No dump/train/convert/bench/registry/ComfyUI/Ollama/router work from this draft.

Operator next decision: review the 32 unapproved educational pairs and explicitly approve or replace them. This does not unpark TurboSparse.
