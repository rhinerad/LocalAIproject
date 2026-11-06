# 2026-08-30 — TurboSparse 4-bit shard-load stall: root cause and streaming fix

## Root cause

The stall at Transformers' `Loading checkpoint shards` **2/4** was **not** a Bamboo
import failure, a FlashAttention scanner hang, a bitsandbytes/sm_120 deadlock, or
a Windows inability to open shard 2.

Evidence on this host (RTX 5080 / sm_120, 32 GiB RAM, ~15 GiB free, GPU idle):

| Hypothesis | Result |
|---|---|
| 1. Custom Bamboo remote-code incompatibility | **Rejected.** `BambooConfig` / 1-layer and 32-layer construct succeed with `trust_remote_code` and the existing `check_imports` bypass. |
| 2. Transformers/bitsandbytes version mismatch as a hard API break | **Not the hang.** `transformers==4.41.2` + `bitsandbytes==0.50.2` NF4-quantizes a 4096×4096 matrix in 0.3 s and 4096×14336 in 1.2 s. |
| 3. CPU RAM / pagefile pressure | **Primary.** ~15 GiB free physical RAM. Each shard is 4.55–4.65 GiB. |
| 4. Incorrect device-map behavior | **Trigger, not a mis-map.** `device_map={"": "cuda:0"}` is the intended 4-bit measurement placement. Combined with (5) it keeps a whole shard in the working set while CUDA pins copies. |
| 5. Safetensors shard loading | **The mechanism.** Transformers 4.41.2 calls `safetensors.torch.load_file` (full 4.5 GiB mmap) then `param.to(float16)` + `Params4bit(...).to(cuda)` for every tensor **before** tqdm advances. `safe_open` + `get_tensor` on shard 2 is milliseconds; `load_file` returns immediately because it is mmap, then touching/quantizing the whole mapping pages ~4.5 GiB and looks frozen at 2/4. |
| 6. Flash-attention/import scanning | **Already mitigated** in the original script; eager attention is used. |
| 7. Other | Contributing: `create_quantized_param` copies `old_value.__dict__` into `Params4bit` (4.41 vs bnb 0.50). Accelerate 1.14 is installed but the stall is Transformers' own shard loop, not `dispatch_model`. |

A later `from_pretrained` of the **full** 15 GiB CPU copy would hit the same host-RAM ceiling. The v2 editor therefore streams safetensors on CPU and never instantiates the 15 GiB `nn.Module` for writing.

## Fix (source checkpoint never written)

New files, original `abliterate_turbosparse.py` left in place:

- `tools/powerinfer/abliterate_loader.py` — one-tensor `safe_open` load, NF4 on CUDA, wall-clock `Deadline`
- `tools/powerinfer/abliterate_turbosparse_v2.py` — same Projected Abliteration math; `--smoke` cannot write a checkpoint
- `tools/powerinfer/diagnose_turbosparse_loader.py` — bounded read-only diagnosis (`--max-seconds`)
- `tools/powerinfer/test_abliterate_projected_math.py`
- `tools/powerinfer/test_abliterate_loader_smoke.py` (subprocess timeout 180 s + 15 s grace)

Math (unchanged):

```
r = μ_harmful − μ_harmless
projection_scalar = dot(r, normalize(μ_harmless))
refined = r − projection_scalar * normalize(μ_harmless)
refined_direction = normalize(refined)
```

Only `o_proj.weight` is edited. The writer update is still `W ← (I − α ddᵀ) W` with
Frobenius-norm restore; the rescale is computed in float32 so bf16 storage does
not drop the scale (first staging dir drifted ~0.74% on two layers).

Hub downloads are refused. `Tiiny/TurboSparse-Mistral-Instruct` resolves only to
the local snapshot
`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-instruct-source-20260830`.

## Verification

- Calibration validator: 8 synthetic pairs accepted.
- CPU math tests: `math-ok`.
- Bounded smoke (`--smoke --max-seconds 180`): 1-layer NF4 load + 8 pair forwards in 10.7 s; `wrote_checkpoint: false`.
- Full v2 run: all four shards streamed (288 Linear4bit, 355 tensors, shard 2/4 progressed), then CPU shard edit of 32 `o_proj` matrices.

Canonical output (use this one):

`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

| Check | Result |
|---|---|
| Source shard byte sizes unchanged | 4991906048 / 4890752392 / 4914328152 / 1173924096 |
| Manifest SHA-256 vs live tree | match |
| `o_proj.weight` changed | 32 / 32 |
| `down_proj.weight` unchanged | 32 / 32 |
| Max Frobenius-norm relative drift | 2.10e-4 |
| Config/tokenizer reload from output | `model_type=bamboo`, `hidden_act=relu`, 32 layers |
| Streaming 1-layer model reload + forward | finite hidden `[1, 3, 4096]` |

Do **not** use `...\turbosparse-mistral-abliterated-projected-20260830` (no `b`): that
earlier staging dir used bf16 rescale and is not the norm-preserving canonical copy.

A full 32-layer `AutoModelForCausalLM.from_pretrained(..., device_map={"": "cpu"})`
reload was **not** used for verification; that is the original RAM-pressure path.
Reload evidence is config/tokenizer + streamed 1-layer module load + shard tensor audit.

## Checkpoint claim

A **mechanically valid** edited checkpoint was written to `...-20260830b` with matching
manifest hashes and a successful bounded model reload.

It is **not** scientific evidence of a refusal direction. Calibration was
`calibration_pairs.synthetic.jsonl` (eight synthetic rows). PowerInfer predictors
and activations must be regenerated before any quality claim.

No files in the source snapshot were overwritten. ComfyUI was not started.
