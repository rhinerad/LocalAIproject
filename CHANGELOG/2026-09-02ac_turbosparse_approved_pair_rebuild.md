# 2026-09-02ac - TurboSparse approved-pair immutable rebuild (edit + calib + dump + bounded train)

## What

Operator Rhine said "go ahead" on 2026-09-02 ~18:23 America/New_York after being told dump/train needed a separate GPU go-ahead. This run built a new immutable projected-edit bundle from the 32 approved pairs, then calibrated, dumped activations, and trained bounded first-pass predictors. Convert, quantize, bench, serve, and registry/Ollama/router were not run.

## Identity

- buildId: `turbosparse-approved-20260902-182522`
- bundle: `A:\PowerInferModels\turbosparse-mistral-instruct\turbosparse-approved-20260902-182522`
- edited: `A:\PowerInferModels\turbosparse-mistral-instruct\turbosparse-approved-20260902-182522\source\edited`
- pairs: `review-only/turbosparse-mistral-projected-abliteration/approved-calibration-32-pairs.2026-09-02.jsonl`
- approval_id: `operator-approval-20260902`
- raw source (read-only `--model`/`--source`): `A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-instruct-source-20260830`

## Validator / preflight

`validate_approved_calibration_pairs.py`: `{"pairs": 32, "approval_id": "operator-approval-20260902", "status": "approved_input"}`

`preflight_turbosparse_rebuild.py`: `ready_for_explicit_gpu_approval`; architecture bamboo/relu hidden_size 4096 intermediate_size 14336 32 layers; prompt_contract_sha256 `151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`.

## Abliteration

`abliterate_turbosparse_v2.py --max-seconds 7200` exit 0, status staged, 32 `o_proj` tensors changed.

`abliteration_manifest.json`: pairs=32, calibration_gate `{pairs:32, approval_id:operator-approval-20260902, status:approved_input}`, hidden_act=relu, architecture=bamboo, projection_scalar~-21.099.

`tokenizer.save_pretrained` clobbered ChatML `tokenizer_config.json` / `tokenizer.json` after `edit_shards_cpu` had copied them. Restored those two sidecars from the read-only source into `$edited` (source and parked 20260830b not written). Prompt contract recapture: `verified_local_contract`, sha256 `151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`.

## Calib / dump / train

- calib: C4 8000 docs, jsonl_sha256 `b8e285b6972c7fd64026c37596c84b1a388a90625ec78fc79030f03d357aa6f4`. Used Windows PowerShell 5.1 because `pwsh.exe` is not installed.
- dump: pipeline default `--max-samples 400000` hung after ~73k samples (472 GiB memmaps on 32 GiB RAM, GPU 6180 MiB / 0% util). Incomplete 400k maps removed. Restarted detached `dump_activations.py --max-samples 25000 --load-4bit` to match the bounded trainer. `profile_meta.json`: n_written 25000 on all 32 layers, 32 `activation_L.pt`, wall~141s.
- train: `resume_calibration_guarded.ps1` cannot run as-is (`pwsh.exe` missing). Equivalent guarded loop called `train_predictor_layer.py` layers 0-31, N=25000, rank=256, batch=256, epochs=2, StartMaxC=70, EmergencyC=82. All 32 `predictor_raw/model_{L}.pt` written; `assemble_predictor.py` assembled `bundle/predictor`.

STOP. No convert, quantize, package, bench, serve, or production registry change.

## Untouched

- parked 8-pair evidence `A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
- non-`b` `...20260830` tree
- raw source (read-only input only)
- review-only UNAPPROVED drafts
- Ollama / router / ComfyUI

## GPU

Pre: RTX 5080 31 C, 51 MiB / 16303, util 0%; ChatGPT.exe 3492, brave 15212, brave 23628 (display leftovers).

Observed temp range: 29-38 C (max 38 C during the hung 400k dump). Never approached StartMaxC 70 or EmergencyC 82. No THERMAL STOP.

Post: 29 C, 53 MiB / 16303, util 0%, same ChatGPT/Brave leftovers. VRAM released after dump and after train.
