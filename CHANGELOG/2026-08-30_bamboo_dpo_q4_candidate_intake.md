# 2026-08-30 — Bamboo-DPO Q4 PowerInfer candidate intake verified

## What changed

- Added the candidate-only intake command
  `tools/powerinfer/intake_bamboo_dpo.py`.
- Added `q4_runtime` mode to `verify_bamboo_dpo_intake.py`; it verifies the
  full original and predictor trees plus the Q4 PowerInfer GGUF, 32 activation
  files, and supporting GGUF metadata. It intentionally does not require the
  redundant dense/FP16 GGUF variants on this 16 GB candidate path.
- Added safe `--resume` support. It only continues the same existing bundle
  after checking its stored plan against the immutable metadata lock; it cannot
  create a second or differently pinned intake.
- Downloaded and verified the approved candidate at:

  `A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake`

## Exact locked receipt

| Role | Resolved repository | Immutable revision |
|---|---|---|
| Original | `Tiiny/Bamboo-DPO-v0_1` | `200c173716a059eaa29d6820a09b3bde76a727ed` |
| Predictor | `Tiiny/Bamboo-DPO-v0.1-predictor` | `13bd167368ef19e3edcacf523909973c78027a98` |
| Q4 PowerInfer runtime | `Tiiny/Bamboo-DPO-v0.1-gguf` | `c3847e080bd8664f2ea299400f74665ca5b13824` |

The intake plan totals **22,140,209,269 bytes** before the vault's 20% free
space margin. The local verification report is `valid: true`, profile
`q4_runtime`, and covers all three receipt roots. Source evidence locks were
written after verification:

- original: 29 files, combined SHA-256
  `a8a74ed18b3a58783c7931d50fedf47334cc4a5b616b865eb7f7b337cc87ecf7`
- predictor: 71 files, combined SHA-256
  `bd9ba4db6168b2ba8de18497f54a92f5c9e3d6ea0aa8959ff9d5330a91dbcd03`
- GGUF runtime: 77 files, combined SHA-256
  `da26c38c88a9357d03a4e6e253de055105dbfda9f478c056e465ed457fd357b2`

## Verification

- The metadata-lock verifier passed before intake.
- `test_verify_bamboo_dpo_intake.py`: **3 tests passed**, including a refused
  mismatch and the Q4-only selection check.
- Candidate manifest status is `candidate`; local hash verification is true.
- Post-intake GPU observation: **29 C, 0% utilization, 102 MiB**. No model was
  loaded and no PowerInfer/ComfyUI server was started.

## Still unverified and prohibited

This does **not** prove instruction following, latency, thermal performance, or
activation topology beyond the public `bamboo` identifier. The candidate is not
registered, exposed in the picker, routed by `router.py`, served through the
proxy, or allowed to start a backend. A separate GPU approval, isolated
mechanical gate, fixed ten-case quality comparison, and explicit promotion
decision are required before any of those actions.
