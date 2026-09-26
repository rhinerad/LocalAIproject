# 2026-08-30 — Bamboo-DPO candidate provenance precheck

## What changed

- Added `tools/powerinfer/BAMBOO_DPO_INTAKE_PRECHECK.md`, a research-only
  provenance record for the next possible PowerInfer quality-gate candidate.
- Added `tools/powerinfer/bamboo_dpo_intake_manifest.template.json`, a
  fail-closed manifest for a future explicitly approved intake.
- Added `tools/powerinfer/record_bamboo_dpo_metadata.py` and the dated
  `bamboo_dpo_remote_metadata_2026-08-30.json` lock. It queries metadata only
  and validates the expected three source shards, 32 predictor files, 32
  activation files, and FP16 PowerInfer GGUF fingerprint.
- Added `tools/powerinfer/verify_bamboo_dpo_intake.py`, which locally compares
  a future staged original/predictor/GGUF tree to that lock before any model
  loading is possible. Its two offline fixtures cover both a byte-for-byte
  match and a refused mismatch.
- Corrected the current PowerInfer status wording: Bamboo-DPO is publicly
  identified as `bamboo`; its exact activation topology must not be called
  dReLU without frozen configuration evidence.
- Tightened the corresponding TODO and handoff notes. No model status changed.

## Why

The prior handoff described the candidate as dReLU even though the source
material available to this project only identifies the architecture as
`bamboo`. The upstream source/repository names also use both `v0.1` and
`v0_1`. Guessing across either difference could cause a wrong predictor or GGUF
to be treated as a matched PowerInfer bundle.

## Evidence

- `https://github.com/Tiiny-AI/PowerInfer` documents Bamboo as a supported
  architecture and describes a PowerInfer GGUF as model plus predictor weights.
- `https://huggingface.co/PowerInfer/Bamboo-DPO-v0_1/tree/main` shows the
  original repository as `bamboo`, Apache-2.0, and visible short main revision
  `200c173`.
- `https://huggingface.co/PowerInfer/Bamboo-DPO-v0.1-predictor` identifies the
  predictor repository and Apache-2.0 license.
- `https://huggingface.co/Tiiny/Bamboo-DPO-v0.1-gguf` identifies its original
  model as `PowerInfer/Bamboo-DPO-v0_1` and exposes the current GGUF hosting
  alias.
- The public model metadata API resolved immutable revisions to
  `200c173716a059eaa29d6820a09b3bde76a727ed` (original),
  `13bd167368ef19e3edcacf523909973c78027a98` (predictor), and
  `c3847e080bd8664f2ea299400f74665ca5b13824` (PowerInfer GGUF). The dated
  lock records each published LFS SHA-256 and size.

## Verification

`python tools/powerinfer/record_bamboo_dpo_metadata.py --verify
tools/powerinfer/bamboo_dpo_remote_metadata_2026-08-30.json` verifies the
schema, full revisions, three source shards, all 32 predictor files, all 32
activation files, and the published FP16 PowerInfer GGUF SHA-256. The record is
metadata-only and does not contact a model endpoint, load GPU memory, download
artifacts, start a server, or alter ComfyUI.

`python tools/powerinfer/test_verify_bamboo_dpo_intake.py` ran two local
fixtures: matching Git-blob/SHA-256 content is accepted and a changed small
repository file is refused. This test uses temporary files only.

## Still unverified

The public revisions and published file hashes are recorded, but local re-hash,
exact activation topology, tokenizer chat template, license text captured from
the frozen files, and original/predictor/GGUF lineage verification remain
mandatory before an operator-approved intake. No quality or performance claim
is made.
