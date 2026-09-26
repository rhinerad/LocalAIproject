# 2026-09-01 — Bamboo-DPO bounded raw-completion diagnostic

## Authorized scope

The operator approved the next GPU-intensive PowerInfer step. TurboSparse was
not eligible because its parked `20260830b` edit still has only eight synthetic
calibration pairs instead of the required 32 approved pairs. The executed step
was therefore the separately bounded **Bamboo-DPO Q4 raw-completion diagnostic**.

## Receipt

The runner produced this immutable candidate-only receipt:

`A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake\validation\bamboo_dpo_raw_completion_20260901_113452.json`

Recorded facts:

- exit code `0`; one prompt, maximum 48 generated tokens;
- locked model SHA-256:
  `9661890635b4f986ebe523eba10404cbb5481be57266cb6d5a894fb63cac527c`;
- native sparse model and CUDA evidence both true;
- sparse FFN GPU offload: **3,024 MiB**;
- native log reported total VRAM use: **7,507.81 MiB**;
- GPU returned to its **69 MiB** idle baseline after process exit;
- ComfyUI port 8188 remained closed;
- `completed_unscored: true`, `promotion_allowed: false`.

The output is preserved only in the receipt's timestamped logs. It is raw
continuation evidence, not an instruction-following, chat, tool-calling, or
quality result.

## Runner reliability correction

The command host initially reached its short execution window while the script
was finalizing. Its receipt was later confirmed present and valid. A separate
detached retry did **not** load a second model: it stopped at a missing
`Get-FileHash` cmdlet in that Windows PowerShell host.

`tools/powerinfer/run_bamboo_dpo_raw_completion_diagnostic.ps1` now uses an
in-process .NET SHA-256 helper instead of `Get-FileHash` when writing the
receipt. The script's PowerShell parser passed after the change. This improves
receipt reliability across interactive and detached hosts; it does not alter
model arguments, candidate files, registry state, routing, proxy, picker, or
the raw-completion-only boundary.

The PowerInfer regression group passed (**41 tests**) after the script change.
The local retrieval index was rebuilt to **341 files / 797 chunks**, and the
H3 validator remained **124/124 valid**.

## What remains blocked

Bamboo-DPO has no source-backed chat template or instruction format. It stays
candidate-only and unregistered. No server, proxy, registry, router, picker,
ComfyUI process, or local-agent PowerInfer route was started or changed.
