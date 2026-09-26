# 2026-08-31 — TurboSparse predictor and agentic-gate preparation

## What changed

- Added `turbosparse-mistral-instruct` as a dedicated Bamboo/ReLU PowerInfer
  target. It is not a picker, proxy, or router entry.
- The pipeline now passes `trust_remote_code` only for that reviewed local
  Bamboo source and validates its `model_type=bamboo`, ReLU activation, and
  4096/14336/32 shape contract.
- Added a fail-closed source-lineage gate: an operator-approved JSONL alone is
  insufficient. Predictor generation also requires an immutable source
  `abliteration_manifest.json` with `approved_input` and at least 32 pairs.
  The supplied JSONL must also SHA-256 match the source checkpoint's copied
  calibration file, preventing a later pair-file substitution.
  Consequently the existing `20260830b` checkpoint remains parked; its eight
  synthetic pairs cannot be retroactively upgraded.
- Added `capture_turbosparse_prompt_contract.py`, a read-only contract receipt.
  It verified the exact local tokenizer hash
  `151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea` and
  recorded that TurboSparse uses ChatML markers, not a generic Mistral
  `[INST]` wrapper.
- Added `turbosparse_agentic_quality_gate.py`: a two-turn, exact-JSON,
  loopback-only capture harness. It never starts a model or executes tools.
- The quality packet is bound to a verified prompt-contract receipt; the
  production registry now refuses this instruct candidate unless that exact
  contract and a passed agentic gate are present in the build's validation
  evidence.
- Added `preflight_turbosparse_rebuild.py`, a no-GPU/no-write readiness check
  for the raw source, reviewed 32-pair JSONL, checkpoint template, and an
  unused immutable output path.
- Corrected `record_acceptance_gate.py` so a future TurboSparse benchmark uses
  the checkpoint ChatML format and its `<|im_end|>` stop marker rather than
  accidentally falling through to `[INST]`. It now retains a completion only
  in memory to render the next benchmark turn, then excludes response text
  from the persisted receipt.

## Verification

- `python -m unittest tools\\powerinfer\\test_turbosparse_agentic_quality_gate.py tools\\powerinfer\\test_record_acceptance_gate.py tools\\powerinfer\\test_preflight_turbosparse_rebuild.py tools\\powerinfer\\test_quality_comparison.py tools\\powerinfer\\test_production_registry.py` — 16 passing tests.
- PowerInfer virtual environment: projected-math and streaming-loader tests
  passed, and all changed Python files compiled.
- `run_pipeline.ps1 -ModelId turbosparse-mistral-instruct -Stage show` resolved
  the target and immutable source without launching GPU work.

## Not done

No approved calibration pairs were created, no new edit was written, and no
GPU dump/train/convert/benchmark/server was started. No model was registered
or routed into the local agent.
