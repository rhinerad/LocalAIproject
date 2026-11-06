# Bamboo-DPO 7B — provenance precheck (research only)

**Status:** Q4 runtime candidate received and byte-verified; the isolated
mechanical gate passed on 2026-08-30. The quality gate remains blocked.

This is the next *candidate* after the ReluLLaMA quality failure. It is not
loaded, registered, available in the chat picker, or allowed to start the
native PowerInfer server. This record deliberately does not turn a public
model-card claim or a byte-verified receipt into a local acceptance claim.

## What the upstream material establishes

| Role | Public upstream identity | Current evidence | Intake interpretation |
|---|---|---|---|
| Original weights | logical `PowerInfer/Bamboo-DPO-v0_1`; resolved `Tiiny/Bamboo-DPO-v0_1` | `200c173716a059eaa29d6820a09b3bde76a727ed`; `bamboo`, custom code, Apache-2.0. | This is the only acceptable original-weight revision unless an upstream rename resolves to this exact immutable revision. |
| Predictor | logical `PowerInfer/Bamboo-DPO-v0.1-predictor`; resolved `Tiiny/Bamboo-DPO-v0.1-predictor` | `13bd167368ef19e3edcacf523909973c78027a98`; Apache-2.0; `model_0.pt` through `model_31.pt`. | It must be copied and locally re-hashed against the provenance lock; a name match is not enough. |
| PowerInfer GGUF | logical `PowerInfer/Bamboo-DPO-v0.1-gguf`; resolved `Tiiny/Bamboo-DPO-v0.1-gguf` | `c3847e080bd8664f2ea299400f74665ca5b13824`; Apache-2.0; 32 activation files and the FP16/Q4_0 PowerInfer GGUFs. | Treat the PowerInfer/Tiiny namespace difference as a verified hosting alias, not permission to substitute another GGUF. |

The current PowerInfer source explicitly supports the `bamboo` architecture and
describes PowerInfer GGUF as carrying both model and predictor weights. Its
older model instructions pair Bamboo-DPO original weights with the predictor
repository above and describe conversion to `*.powerinfer.gguf` plus activation
statistics.

## Verified architecture; chat format still unknown

The received frozen original revision now establishes dReLU directly:
`modeling_bamboo.py`'s `BambooMLP.forward()` evaluates
`relu(gate_proj(x)) * relu(up_proj(x))` before `down_proj`; `config.json` sets
`hidden_act: relu`. It is therefore correct to call this exact locked candidate
**Bamboo dReLU**.

The frozen tokenizer has **no `chat_template`**. Do not infer an `[INST]`,
Alpaca, or other chat wrapper from the `DPO` name. The isolated mechanical
gate used a raw continuation only. Establish a prompt contract before any
instruction/format quality comparison.

The frozen-evidence classifier has now recorded
`validation/bamboo_dpo_prompt_contract_20260830_233100.json` with
`prompt_contract_unresolved`. Consequently, chat routing and the fixed
instruction-following quality packet are blocked rather than guessed.

## Recorded remote provenance lock

`bamboo_dpo_remote_metadata_2026-08-30.json` was generated through the public
metadata API only. It records the full revisions above, every published LFS
SHA-256 and size, the three original safetensors shards, 32 predictor files,
32 activation files, and the selected FP16 PowerInfer GGUF. Re-run it only to
refresh a *new* explicit research record; do not overwrite this dated lock.

```powershell
python tools\powerinfer\record_bamboo_dpo_metadata.py --verify `
  tools\powerinfer\bamboo_dpo_remote_metadata_2026-08-30.json
```

## Required immutable local intake record

Copy `bamboo_dpo_intake_manifest.template.json` into a new build directory only
after the operator expressly approves an intake. The record is invalid until
all of the following are present:

1. The three full revisions recorded above, with the dated remote provenance
   lock copied into the new build evidence directory. A newer `main` tip is not
   an acceptable substitute.
2. Local SHA-256 digests for every received original safetensors shard,
   config/tokenizer custom code, each predictor artifact, every activation
   statistic, and the selected `*.powerinfer.gguf` file. Each must match the
   public lock (or quarantine the mismatch).
3. A source-to-predictor-to-activation lineage check proving the predictor and
   activation files came from the same declared Bamboo-DPO build, not merely
   from a similarly named 7B model.
4. The license text and model-card terms captured from those exact revisions.
5. The inspected architecture and chat-template result. `bamboo` and dReLU
   must match the frozen received code; the chat template remains absent until
   an evidence-backed prompt contract is established.
6. A human approval ID, date, and intended *candidate-only* scope.

Any missing field blocks the next step. A generic llama.cpp/Ollama Q4_0 file,
an ordinary dense 7B model, or a Qwen checkpoint is not an equivalent PowerInfer
candidate.

## Permitted next action after approval

Perform read-only metadata resolution and a hash-recorded source intake into the
encrypted PowerInfer vault. Then run the existing isolated mechanical gate and
the fixed ten-case instruction/format comparison. Keep the bundle unregistered
unless both gates pass and the operator separately approves a registry entry.

Before any model load, compare the local received files to the dated lock:

```powershell
python tools\powerinfer\verify_bamboo_dpo_intake.py `
  --original <staged-original-root> `
  --predictor <staged-predictor-root> `
  --gguf <staged-gguf-root> `
  --out <candidate-build>\validation\bamboo_dpo_local_hash_verification.json
```

The verifier is local-only. It computes SHA-256 for LFS files and the correct
Git blob SHA-1 for small repository files, then refuses missing or changed
content. A `VALID` result proves a local byte match to the recorded public
metadata; it does not make the candidate production-ready.

For the approved 16 GB runtime intake, use the candidate-only Q4 subset
(original source + predictor + `Q4_0.powerinfer.gguf` + 32 activation files):

```powershell
python tools\powerinfer\intake_bamboo_dpo.py `
  --vault A:\PowerInferModels --execute
```

It requires about 22.14 GB of artifacts plus the vault margin. If a transfer is
interrupted before verification, it writes no acceptance state; resume only the
same revision-pinned bundle with `--resume`. The command never imports model
weights, starts a backend, touches GPU memory, or changes the local-agent route.

## Approved receipt and remaining boundary

The explicitly approved Q4 runtime receipt is at
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake`; see
`CHANGELOG/2026-08-30_bamboo_dpo_q4_candidate_intake.md`. It is candidate-only.
The approval applied to that exact pinned intake, not to substitutes, newer
revisions, dense/FP16 variants, or any model-execution step.

## Not authorized by this record

- further downloads or any substitute/newer source revision;
- loading a model;
- GPU dump, training, conversion, benchmark, or server launch;
- modifying the PowerInfer production registry, proxy, router, or model picker;
- replacing the paused Equal Shares workflow or starting ComfyUI.

## Public sources consulted

- `https://github.com/Tiiny-AI/PowerInfer` — supported architecture, model
  lineage, and PowerInfer-GGUF/predictor relationship.
- `https://huggingface.co/PowerInfer/Bamboo-DPO-v0_1/tree/main` — original
  repository identity, visible short revision, architecture, and license.
- `https://huggingface.co/PowerInfer/Bamboo-DPO-v0.1-predictor` — predictor
  repository identity and license.
- `https://huggingface.co/Tiiny/Bamboo-DPO-v0.1-gguf` — currently visible GGUF
  hosting alias and stated original-model relationship.
