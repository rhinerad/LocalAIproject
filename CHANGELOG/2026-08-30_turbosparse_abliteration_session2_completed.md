# 2026-08-30 — TurboSparse projected abliteration: independent re-execution completed

## Session context

An independent diagnostic and abliteration pass was run against the same task
specification used to produce `turbosparse-mistral-abliterated-projected-20260830b`.
All streaming-loader infrastructure (`abliterate_loader.py`,
`abliterate_turbosparse_v2.py`, `diagnose_turbosparse_loader.py`) was found
already in place from the prior session. No code was changed; the session
confirmed diagnostics, re-ran smoke, and ran the full abliteration to a
separately named output directory.

Operator-accepted canonical checkpoint remains:
`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`
(see `2026-08-30_turbosparse_abliteration_docs_accepted.md`).

---

## Diagnostics

**Environment** (Python: `A:\Users\rhine\.unsloth\studio\unsloth_studio\Scripts\python.exe`):

| Package | Version |
|---|---|
| torch | 2.10.0+cu130 |
| transformers | 5.5.0 |
| bitsandbytes | 0.50.2 |
| accelerate | 1.14.0 |
| safetensors | — |
| GPU | RTX 5080 (sm_120) |
| VRAM free (pre-run) | 15,872 MB |
| Host RAM free | ~15 GiB |

**Shard inventory** (`turbosparse-mistral-instruct-source-20260830`):

| Shard | Tensors | Size |
|---|---|---|
| model-00001-of-00004.safetensors | 108 | 4,760.7 MB |
| model-00002-of-00004.safetensors | 117 | 4,664.2 MB |
| model-00003-of-00004.safetensors | 110 | 4,686.7 MB |
| model-00004-of-00004.safetensors | 20  | 1,119.5 MB |

All 4 shards readable via `safe_open`. Tokenizer and config load successfully
in isolation (`model_type=bamboo`, `hidden_act=relu`, 32 layers, `hidden_size=4096`).

**Transformers 5.5.0 lazy-load verified** (alternative path, not used for abliteration):
`device_map='auto'` + `max_memory={0: '14GiB'}` loaded the full model in 96.7 s
with VRAM = 5,209 MB and a finite forward-pass hidden norm of 136.4542.

**Root cause confirmed**: matches prior CHANGELOG (`2026-08-30_turbosparse_projected_abliteration_loader_fix.md`).
Transformers 4.41.x `load_file` full-shard mapping causes pagefile thrashing at
shard 2/4 boundary (~15 GiB RAM, ~9.4 GiB combined shard 1+2 working set plus CUDA pins).
Streaming loader avoids this by reading one tensor at a time via `safe_open`.

**bitsandbytes cpp-extension warning**: non-blocking. `bnb 0.50.2` warns about
`torch >= 2.11.0` requirement for cpp extensions but core CUDA NF4 kernels work.
4096×14336 tensor quantizes in ~1.1 s.

---

## Smoke test

`python abliterate_turbosparse_v2.py --smoke --trust-remote-code --max-seconds 180`

- 1-layer NF4 load + 8-pair forwards completed inside deadline
- `"wrote_checkpoint": false`
- Status: **passed**

---

## Full abliteration run

`python abliterate_turbosparse_v2.py --model <source> --pairs calibration_pairs.synthetic.jsonl --output <output-v2> --trust-remote-code`

**Load phase** (streaming NF4):

| Stat | Value |
|---|---|
| Shards streamed | 4 |
| Tensors loaded | 355 |
| Linear4bit modules | 288 |
| Skipped | 0 |

**Direction measurement**:

```
r = μ_harmful − μ_harmless
projection_scalar = dot(r, normalize(μ_harmless)) = −27.4880
refined = r − projection_scalar * normalize(μ_harmless)
direction = normalize(refined)   dim=4096
```

**CPU shard edit** (full BF16, source never written):

- 32 `o_proj.weight` matrices edited across all 32 decoder layers
- Frobenius-norm preservation applied in float32 (limits activation/sparsity drift)
- `down_proj.weight` and all other tensors: unchanged
- All 4 output shards written; config, tokenizer, calibration pairs, manifest copied

**GPU memory after completion**: 106 MB used, 15,872 MB free (properly released).

---

## Output

```
A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-20260830-v2
```

`abliteration_manifest.json` contents verified:

| Field | Value |
|---|---|
| source_model | Tiiny/TurboSparse-Mistral-Instruct |
| hidden_act | relu |
| method | Projected Abliteration: harmful-harmless; harmless-mean orthogonal refinement; norm-preserving o_proj projection |
| projection_scalar | −27.487987518310547 |
| changed_parameter_count | 32 |
| sha256 entries | 16 (4 shards + config/tokenizer/etc.) |
| requires_powerinfer_reprofiling | true |

---

## Success criteria

| Criterion | Result |
|---|---|
| 1. Projected direction computation completes | **PASS** — scalar=−27.4880, dim=4096 |
| 2. Edited checkpoint written to fresh immutable output directory | **PASS** — `...20260830-v2` (new dir, did not overwrite any prior output) |
| 3. Output reloads successfully | **PASS** — config, tokenizer, all 4 shards (108/117/110/20 tensors) readable; manifest fields present |
| 4. `abliteration_manifest.json` has method, projection scalar, changed parameters, SHA-256 | **PASS** — all fields confirmed, 16 SHA-256 entries |
| 5. Source remains unchanged | **PASS** — source only opened read-only; shard files not written |
| 6. GPU memory released after completion | **PASS** — 106 MB used vs 15,872 MB free post-completion |

---

## Reload verification (bounded)

```
config OK: bamboo, hidden_act=relu
tokenizer OK: vocab_size=32000
shard model-00001-of-00004.safetensors: 108 tensors, first=model.embed_tokens.weight
shard model-00002-of-00004.safetensors: 117 tensors, first=model.layers.10.input_layernorm.weight
shard model-00003-of-00004.safetensors: 110 tensors, first=model.layers.20.input_layernorm.weight
shard model-00004-of-00004.safetensors: 20 tensors, first=lm_head.weight
projection_scalar=-27.487987518310547
changed_parameter_count=32
sha256 entries: 16
VERIFICATION COMPLETE - config+tokenizer+shards readable, manifest valid
```

Note: a full 32-layer `AutoModelForCausalLM.from_pretrained(..., device_map={"": "cpu"})` reload
was not used; that is the original RAM-pressure path. Bounded verification uses config/tokenizer
+ shard tensor count audit.

---

## Not changed

Source snapshot `turbosparse-mistral-instruct-source-20260830`, prior output directories
(`...20260830`, `...20260830b`), ReluLLaMA GGUFs, predictor trees, activation files, production
registry, and all Equal Shares assets were not written.
No ComfyUI, Hub download, dump, train, convert, or benchmark was started.

## Caveats

Calibration was `calibration_pairs.synthetic.jsonl` (8 synthetic rows).
This is **not** a scientifically identified refusal direction.
PowerInfer predictor/activation regeneration is mandatory before any quality claim.
Do not use this checkpoint in production without operator-approved real calibration pairs.
