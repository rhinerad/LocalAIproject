# PowerInfer status — 2026-08-30

2026-09-08e finish-prove: evidence gates proven (32 unit tests; physical audit
reconfirmed 139/126/0/0). Semantic QA still not_run; no production. See
../CHANGELOG/2026-09-08e_prompt_pack_evidence_finish_prove.md and
../docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md. No PowerInfer assets touched.

2026-09-08 prompt-pack QA status: see
../docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-08.md and the generated
../HANDOFF_STATUS.md. Production is paused for current-prompt stills, exact VLM
semantic QA, and explicit still approval. No PowerInfer weights, predictors,
registry, router settings, or runtime were changed in that debugging pass.

2026-09-08d educational UNAPPROVED draft: see `../review-only/turbosparse-mistral-projected-abliteration/` and `../tools/powerinfer/STATUS.md`. 32 educational pairs drafted with `operator_approved: false` / `approval_id: null`. Draft validator `validate_calibration_pairs.py --draft` accepts; approved gate rejects. TurboSparse still parked. No weights/predictors/registry/router/ComfyUI change.


The RTX 5080 native PowerInfer build and the ReluLLaMA-7B sparse bundle have
passed mechanical serving checks, but the candidate failed the bounded quality
comparison (9/10 elementary instruction/format cases). It remains diagnostic
and must not be registered or routed into the local agent.

## TurboSparse-Mistral projected abliteration (parked)

Canonical edited weights (only this directory):

`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

Do not use `...\turbosparse-mistral-abliterated-projected-20260830` (no `b`).
Do not modify
`...\turbosparse-mistral-instruct-source-20260830`, ReluLLaMA GGUFs, or
predictor/activation artifacts.

The old Transformers stall at shard 2/4 was **host-RAM pressure from full-shard
loading**. The streaming `safe_open` loader is the remediation. Verified on
`20260830b`: 32/32 `o_proj` edited, `down_proj` unchanged, max Frobenius-norm
relative drift **2.1e-4**, Bamboo/ReLU reload, finite one-layer forward.
Calibration used eight synthetic pairs and is exploratory only. Predictors have
**not** been rebuilt. No quality benchmark has been run. No GPU dump, train,
convert, benchmark, or ComfyUI process was started for this checkpoint. Keep it
parked. **Do not rebuild predictors or run production benchmarks** until
operator-approved harmful/harmless pairs exist. Predictor regeneration from
this exact tree is then mandatory before any quality claim.

### Prepared next controlled run (2026-08-31)

The safe groundwork is now present, but the current tree remains deliberately
blocked. `turbosparse-mistral-instruct` has a dedicated Bamboo/ReLU pipeline
target; the runner validates checkpoint ChatML rather than assuming Mistral
`[INST]`, uses the reviewed local Bamboo code only, and refuses predictor work
unless the supplied approved-pair JSONL **and** the source manifest show an
immutable edit created from at least 32 approved pairs.

The verified local prompt contract is ChatML (`<|im_start|>system`, `user`,
`assistant`, `<|im_end|>`), with template SHA-256
`151dcbed9fbd8f6f020e6c12f8cf7c848c1edfc6f7138648b922282e77d6e2ea`.
`tools/powerinfer/turbosparse_agentic_quality_gate.py` is ready to run two
strict JSON tool-call turns against an already-running loopback server after
conversion. It never launches a server or executes the suggested file tools.
The existing 20-turn native acceptance harness was also corrected to render
this same ChatML format and retain responses only transiently between turns;
it does not persist generated text in benchmark evidence.
`preflight_turbosparse_rebuild.py` validates a reviewed pair file, raw source,
contract hash, and unused output location without loading weights or creating
files; it is the required last non-GPU check before an approval request.

The only permitted sequence is: operator-approved pairs → new immutable
projected edit → predictors/activations → conversion → isolated native service
→ agentic quality gate → explicit human review/registry decision. No current
candidate is registered or routed. The registry enforces this for TurboSparse:
an otherwise complete mechanical bundle is refused unless its local prompt
contract and passed JSON tool-call gate are present and cryptographically bound.

The separate official PowerInfer **Bamboo-DPO 7B** candidate now has a passed
isolated native mechanical gate. The frozen `BambooMLP` source verifies dReLU
(`relu(gate) * relu(up)`); the tokenizer has no chat template. Its Q4 GGUF
loaded through native sparse PowerInfer with CUDA and 3,024 MiB FFN GPU offload,
then released VRAM. This is not a quality result and it is not accepted. The
approved Q4 runtime receipt remains candidate-only at
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake`; it is still
candidate-only. The frozen prompt-contract evidence is unresolved (no declared
chat template or instruction format), so the ten-case quality comparison is
blocked rather than run with an invented wrapper. Do not enable an endpoint,
registry, router, or picker entry. See
`tools/powerinfer/BAMBOO_DPO_INTAKE_PRECHECK.md` and
`CHANGELOG/2026-08-30_bamboo_dpo_prompt_contract_gate.md`. The frozen model
code does document a plain raw-continuation example, recorded in
`bamboo_dpo_prompt_contract_addendum_20260831_000001.json`. That permits only
the inert, separately approved
`run_bamboo_dpo_raw_completion_diagnostic.ps1 -Execute` diagnostic; it does
not establish chat routing or instruction-following quality.

The existing Ollama routes remain the production fallback. No render, ComfyUI
job, VLM load, or background worker was started for this evaluation.
