# Upgrade 18 — measured attention and runtime optimization backlog

## Goal

Improve the local desktop agent and ComfyUI performance only where the active
runtime can actually benefit, without breaking the one-GPU-owner rule or
changing a known-good Equal Shares render path.

## Current findings — 2026-08-24

### SageAttention 2: do not install, enable, or replace

The actual Rockernow ComfyUI environment already has
`sageattention 2.2.0+cu130torch2.10.0andhigher.post5`, PyTorch `2.10.0+cu130`,
Triton, and an RTX 5080 (`sm_120`). This is not a missing optimization.

The preserved controlled test in
`A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\optimization_report\SAGEATTENTION_BLACKWELL_FINDINGS.md`
established the exact CUDA KJNodes backend fails with **“no kernel image is
available for execution on the device”**: that wheel carries sm80/sm89/sm90
kernels, not a runnable sm120 kernel. Its Triton alternative passed a numerical
smoke test but made the representative Wan run **4.7% slower** (142.424 s vs
136.001 s) and changed output (average PSNR 22.47 dB). It is rejected.

SageAttention is a PyTorch/ComfyUI attention replacement. The local agent's
chat models run through Ollama and the lazy VLM through CUDA llama.cpp, so
installing or patching SageAttention cannot speed agent conversation, tool use,
or Qwen2.5-VL captioning.

### Original SageAttention v1: rejected

Do not install or switch to the original SageAttention v1. Upstream documents
v1 as a Triton path and explicitly says it is slower than v2, v2++, and v3.
The local v2 test already had to use the Triton alternative on this RTX 5080;
it was 4.7% slower and changed the representative output. Therefore, v1 cannot
be an improvement here: it would replace the rejected path with an older,
slower implementation. This is an inference from the upstream v1 comparison
and the preserved local measurement, not an untested compatibility claim.

The upstream project supports Blackwell only with a compatible build stack and
explicitly warns that not every model can safely replace generic SDPA. Do not
globally add `--use-sage-attention` or insert an attention patch into H3/Wan/Qwen
workflows. See the official [SageAttention project](https://github.com/thu-ml/SageAttention)
and the local measured report above.

## Backlog — highest value first

1. **Measure Ollama Flash Attention + q8_0 KV cache on the GPU reasoning pair.**
   Ollama documents `OLLAMA_FLASH_ATTENTION=1` plus
   `OLLAMA_KV_CACHE_TYPE=q8_0`; q8_0 usually cuts KV-cache memory roughly in
   half with a small precision trade-off. It is relevant to the agent's 20K–32K
   context windows, unlike SageAttention. Run only when ComfyUI is stopped and
   no media job is pending. Measure 14B VRAM, time-to-first-token, output
   correctness on an approved anonymized case, and the ability to yield to a
   render. Keep it only if all checks pass; otherwise retain f16.

   `measure_ollama_kv_cache.py` now provides the guarded, one-request evidence
   harness. It refuses a render-owned/unknown GPU and requires an explicit
   `--run` plus JSON report destination. Start the GPU Ollama service once with
   the baseline configuration and once with the proposed configuration, then
   run the same 20,480-context test for each. It is not an automatic switch.

2. **Repair/verify launcher revision parity before each local-agent release.**
   The desktop launcher compares its expected revision with `/api/status`. This
   release corrected it to r49. `test_launcher_revision.py` now prevents a
   future revision bump from making an otherwise healthy app repeatedly appear
   stale.

3. **Benchmark a future ComfyUI attention backend only with one fixed workflow.**
   A future native ComfyUI backend or a verified sm120 Sage build may be worth
   testing, but only as a clone of a known workflow, one controlled output, and
   measured time/VRAM/visual comparison. It must never alter global launch
   arguments or Equal Shares workflow files first.

4. **Use already verified TensorRT engine reuse where it fits.** The installed
   4x-UltraSharp and RIFE paths have documented reuse results (2.281 s and
   1.263 s respectively) in the local optimization report. This is a ComfyUI
   post-processing option, not an agent-chat acceleration, and must be selected
   per workflow after visual review.

## Explicit non-goals

- No new attention package, CUDA toolkit, PyTorch replacement, global launch
  flag, model download, or automatic benchmark.
- No render start, no H3 workflow edit, and no evidence deletion.
- No concurrency increase: `OLLAMA_NUM_PARALLEL=1` remains correct for the
  16 GB single-GPU ownership policy.
