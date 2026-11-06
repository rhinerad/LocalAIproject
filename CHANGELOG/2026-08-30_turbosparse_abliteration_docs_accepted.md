# 2026-08-30 — TurboSparse projected-abliteration documentation accepted

## Change

Operator accepted the loader diagnosis and checkpoint verification. Living
PowerInfer docs now name the **only** usable edited weights:

`A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-abliterated-projected-20260830b`

Do **not** use `...\turbosparse-mistral-abliterated-projected-20260830` (no `b`).

Recorded facts (no new GPU work this pass):

- Root cause of the Transformers `Loading checkpoint shards` 2/4 stall: **host-RAM
  pressure from full-shard `safetensors.torch.load_file`**, not Bamboo
  incompatibility, bitsandbytes/sm_120 deadlock, FlashAttention scanning, or a
  wrong `device_map`.
- Remediation: the streaming loader in `tools/powerinfer/abliterate_loader.py`
  / `abliterate_turbosparse_v2.py` (one tensor at a time via `safe_open`).
- 32/32 `o_proj.weight` residual-stream writers edited; 32/32 `down_proj.weight`
  matrices unchanged.
- Maximum Frobenius-norm relative drift: **2.1e-4**.
- Bamboo/ReLU config+tokenizer reload succeeded; bounded 1-layer forward produced
  finite hidden states `[1, 3, 4096]`.
- Calibration was `calibration_pairs.synthetic.jsonl` — **exploratory only**, not
  a scientifically identified refusal direction.
- **PowerInfer predictor/activation regeneration is mandatory** before any
  quality claim. Do not dump, train, convert, quantize, or bench this checkpoint
  until operator-approved harmful/harmless pairs exist.

## Files updated (documentation only)

- `CHANGELOG/README.md` — index this entry and the prior loader-fix entry
- `CHANGELOG/2026-08-30_projected_abliteration_math.md` — superseded pointer
- `CHANGELOG/2026-08-30_turbosparse_loader_memory_blocker.md` — superseded pointer
- `tools/powerinfer/README.md` — TurboSparse research-checkpoint section
- `TODO.md` — parked TurboSparse item; no predictor rebuild
- `GROK_STATUS.md` — current coordination note
- `work/POWERINFER_STATUS_2026-08-30.md` — canonical path and stop-conditions
- this file

## Not changed

Source snapshot
`...\turbosparse-mistral-instruct-source-20260830`, ReluLLaMA GGUFs, predictor
trees, activation files, quality packets, production registry, `router.py`,
and the earlier `...20260830` (no `b`) staging directory were not written.
No ComfyUI, dump, train, convert, or benchmark was started.
