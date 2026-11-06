# 2026-08-29 — PowerInfer next-steps runbook now ReluLLaMA / parked ProSparse

## What changed

- `docs/NEXT_STEPS_RUNBOOK_2026-08-29.md` Section 1 (and Section 1B live-PoC paths): live `-ModelId` is now `relu-llama-7b` (`SparseLLM/ReluLLaMA-7B`, `hidden_act` `relu`). Vault example is `C:\PowerInferVault`. CUDA Toolkit 12.8+ (`nvcc`, `sm_120`) and Visual Studio 2022 Desktop C++ are an explicit **STOP** before compile; Developer PowerShell for VS 2022 remains required. ProSparse-7B is parked/retired (FATReLU / `SparseLlamaForCausalLM`); relu-gate on that vault is expected to **fail exit 2**. The runbook now says do not continue past a FATReLU fail and do not bypass the gate.
- `CHANGELOG/README.md`: index line for this entry added at the top.
- `GROK_STATUS.md`: one current-section bullet that the next-steps runbook now matches ReluLLaMA / parked ProSparse.
- Did **not** edit `run_pipeline.ps1`, `pipeline_lib.py`, `check_relu_gate.py`, `models.json`, `TODO.md`, or `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md`. Did **not** run `-Execute`, touch the GPU, download, bypass relu-gate, or continue the parked ProSparse vault.

## Why

Section 1 still told a zero-prior-knowledge operator (and any later LLM) to run `-ModelId prosparse-7b`, expected `D:\PowerInferModels` as the vault, and said relu-gate "should pass almost instantly." That contradicts `tools/powerinfer/models.json` (ReluLLaMA live, `prosparse-7b` `retired: true`), `TODO.md`, and `docs/POWERINFER_FATRELU_OPERATOR_DECISION_2026-08-29.md` (FATReLU / expected exit 2). Leaving it would send Rhine down the parked conversion path.

## The evidence

Before this write, Section 1 title and every pipeline command used `prosparse-7b`; step 1.2 named `D:\PowerInferModels`; step 1.5 said relu-gate should pass and to not continue until it does (no FATReLU stop). After this write, from the same file:

- `-ModelId relu-llama-7b` is the live command id (setup/intake/relu-gate/calib/dump/train/convert/quantize/package/validate/bench).
- `-ModelId prosparse-7b` remains only in **do-not-use** / parked-id warnings, never as a command to run.
- `D:\PowerInferModels` count is 0. Vault example is `C:\PowerInferVault`.
- FATReLU / exit 2 is described as expected for the parked ProSparse vault, with an explicit stop / no-bypass instruction.
- GGUF example in Section 1B is `relu-llama-7b.q4.powerinfer.gguf` under `C:\PowerInferVault\relu-llama-7b\...`.

Sections 2, 3, and 4 were left in place.

## What was verified after

CPU-only string checks on the rewritten runbook (no GPU, no download, no `-Execute`):

```text
relu-llama-7b ModelId commands: 12
prosparse-7b ModelId mentions: 3  (do-not-use / parked warnings only)
D:\PowerInferModels: 0
C:\PowerInferVault: 8
FATReLU: 5
## Section 2 / 3 / 4: present
live stages all use -ModelId relu-llama-7b: show, setup, intake, relu-gate,
calib, dump, train, convert, quantize, package, validate, bench
```

`CHANGELOG/2026-08-29i_powerinfer_runbook_relullama.md` exists. `CHANGELOG/README.md` has this file as the newest index line. `GROK_STATUS.md` current section names the runbook match.

## What is still unverified

- Native RTX 5080 (`sm_120`) compile: CUDA Toolkit 12.8+ and Visual Studio 2022 C++ workload are still absent. This session did not compile PowerInfer and did not run `-Stage setup -Execute`.
- Live PowerInfer sparse latency/VRAM numbers. GPU was not used.
- Relu-gate was not re-run here against the ReluLLaMA vault `config.json` (prior sessions already recorded ReluLLaMA as `hidden_act=relu` / `llama`, and ProSparse as FATReLU exit 2).
- Accepted validation manifests, predictor/activation artifacts, and picker integration. Those stay operator-gated.
