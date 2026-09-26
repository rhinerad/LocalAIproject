# Attention and runtime optimization review — 2026-08-24

## Finding

SageAttention 2 was already installed in the active Rockernow ComfyUI venv:
`2.2.0+cu130torch2.10.0andhigher.post5` with PyTorch `2.10.0+cu130`, Triton,
and an RTX 5080 (`sm_120`). The local optimization report had already tested the
exact KJNodes CUDA backend: it fails because the wheel has no runnable sm120
kernel. The available Triton variant was 4.7% slower than baseline and changed
the representative Wan output, so SageAttention remains disabled.

This does not affect the local agent's Ollama/llama.cpp chat and VLM paths:
SageAttention is a PyTorch attention library, while those paths do not run
inside ComfyUI's PyTorch process.

The original SageAttention v1 was also reviewed and rejected. Its upstream
project describes v1 as the older Triton implementation and slower than the
newer variants. Since the RTX 5080 had already fallen back to Triton for the
v2 test—and that path was slower and changed output—v1 would be a regression,
not a safe workaround.

## Changed

- Added `UPGRADE/18_attention_runtime_optimization_backlog.md`, recording the
  measured Sage result and the safe next experiments.
- Corrected the local-agent launcher’s expected application revision from r46
  to r49, so it recognises the current app rather than unnecessarily treating
  it as stale on every desktop launch.
- Added the findings and the measurement-gated Ollama Flash Attention + q8 KV
  experiment to the upgrade index and durable local-agent memory.
- Recorded that SageAttention v1 must not be installed or substituted for the
  rejected v2 route on this machine.
- Added a guarded GPU KV-cache measurement harness and unit tests. It does
  nothing until explicitly run, refuses a busy/unknown GPU, preserves a JSON
  report, and never starts ComfyUI or a render.
- Added a source-level launcher/server revision-parity regression test, so a
  release cannot silently turn a healthy local agent into a stale-instance
  restart loop.

## Current live-test status

The measurement preflight was intentionally run without `--run`. It confirmed
the GPU server currently has the exact Huihui 8B model but does not have the
required Huihui 14B primary model. No substitution, server restart, model load,
or setting change was made; the 14B comparison remains correctly blocked until
that exact download is present.

## Next safe optimization

The best candidate for the **agent**, not ComfyUI, is a controlled GPU-only
Ollama test of Flash Attention plus q8_0 KV cache. This is deliberately not
enabled in this change: it requires measured 14B VRAM/latency/quality and a
clean yield-to-render check before it can be retained.

## Verification

- Read-only inspection confirmed the installed SageAttention package imports in
  the actual Rockernow venv, with RTX 5080 / CUDA 13.0 detected.
- Reviewed the existing controlled local optimization reports; no render,
  model load, package install, workflow, or evidence file was changed.
- Confirmed `START_LOCAL_AGENT_GUI.ps1` and `server.py` now carry the same r49
  application revision string.
