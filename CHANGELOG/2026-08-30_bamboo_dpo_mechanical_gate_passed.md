# 2026-08-30 — Bamboo-DPO mechanical PowerInfer gate passed

The byte-verified candidate at
`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake` passed one
isolated native PowerInfer mechanical smoke run. The source tree was not
changed. No server, registry, proxy, router, picker, ComfyUI process, render,
training, or conversion was started.

## Frozen candidate facts now confirmed locally

- Exact model SHA-256:
  `9661890635b4f986ebe523eba10404cbb5481be57266cb6d5a894fb63cac527c`
- `BambooMLP.forward()` applies `relu(gate_proj(x)) * relu(up_proj(x))` before
  `down_proj`, so the locked revision is dReLU, not merely an unclassified
  `bamboo` model.
- 32 matching `activation_*.pt` files were present and the local source lock
  remained valid.

## Result

The deterministic raw-completion smoke used a 512-token context, 12 GiB VRAM
budget and 16 generated tokens. Native logs prove PowerInfer sparse loading,
CUDA acceleration, and **3,024 MiB** FFN offload. Load time was 4,186.65 ms;
prompt evaluation was 241.73 tokens/s and generation was 65.86 tokens/s for
this tiny smoke. GPU temperature moved 29 C → 32 C and returned to 30 C with
102 MiB resident after exit.

Evidence is stored next to the candidate:
`validation/bamboo_dpo_mechanical_gate_20260830_232453.json` and its paired
stdout/stderr logs.

The first executable attempt exposed that native PowerInfer invokes literal
`python -m powerinfer` to calculate its split. The system Python did not have
the module, produced zero FFN offload, and is recorded as a mechanical failure.
The gate now scopes the matching repository venv for the child process and
requires successful split plus nonzero FFN offload before reporting a pass.

## Still blocked

This is not an instruction-following or quality result. The frozen tokenizer
has no chat template, so a prompt contract must be established before the fixed
ten-case quality test. The candidate remains `candidate` only and must not be
registered or exposed in the local-agent picker without a separate approval
after that quality gate.
