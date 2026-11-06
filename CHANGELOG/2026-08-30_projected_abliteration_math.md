# 2026-08-30 — Projected Abliteration implementation

**Later the same day:** the shard-load stall was diagnosed as host-RAM pressure
from full-shard loading and remediated with a streaming loader. Canonical
edited weights are
`...\turbosparse-mistral-abliterated-projected-20260830b`. See
`2026-08-30_turbosparse_projected_abliteration_loader_fix.md` and
`2026-08-30_turbosparse_abliteration_docs_accepted.md`. The verification
block below is the pre-fix record and is not current status.

## Change

- `tools/powerinfer/abliterate_turbosparse.py` now measures separate harmful and
  harmless hidden-state means with a 4-bit CUDA copy.
- It computes `r = mu_harmful - mu_harmless`, removes the component parallel to
  `normalize(mu_harmless)`, and normalizes the remaining refined direction.
- Only shape-compatible `o_proj.weight` residual-stream writer matrices are
  edited. Each edit is followed by Frobenius-norm preservation to limit ReLU
  activation/sparsity drift.
- Calibration records and the validator now require `harmful` and `harmless`
  fields. The checked-in eight-row file is synthetic smoke data only; it is not
  evidence that a refusal direction has been scientifically identified.

## Verification

- Calibration validator: 8 pairs accepted.
- Python syntax compilation: passed.
- A controlled 4-bit load was attempted with the exact local
  `Tiiny/TurboSparse-Mistral-Instruct` source. Loading reached shard 2/4 and
  stopped making progress while the model occupied VRAM; the isolated process
  was terminated before any output checkpoint was written.
- Status: implementation staged; checkpoint generation remains blocked by the
  custom Bamboo loader's shard-load stall and requires a separate loader
  investigation. No source files or prior evidence were overwritten.
