# 2026-08-25 — guarded 14B KV-cache baseline and probe correction

## What changed

- Pulled the exact configured primary reasoning model:
  `huihui_ai/qwen3-abliterated:14b` (Ollama, 9.0 GB).
- Ran one guarded 20,480-context baseline request through
  `local_agent/measure_ollama_kv_cache.py` with ComfyUI stopped and the render
  owner released. Evidence is written to
  `local_agent/runtime/benchmarks/ollama_kv_cache_baseline_f16_2026-08-25.json`.
- Corrected `measure_ollama_kv_cache.py` so a benchmark request explicitly
  disables optional model thinking, trims harmless trailing whitespace for the
  exact completion check, and separately records whether the expected marker
  appeared. The harness still does not retain hidden reasoning or response text.
- Added regression coverage for the thinking flag, whitespace normalization,
  and non-exact marker detection.
- Added an explicit `-GpuKvCache flash_q8` launcher candidate. Its default is
  still `baseline`; it configures only a newly-started GPU Ollama server and
  cannot silently alter the CPU tier.
- Added a two-second GUI status snapshot cache. It prevents browser polling
  from repeatedly probing both Ollama inventories during a service restart;
  per-turn GPU/CPU routing remains uncached and authoritative.
- When ComfyUI owns the GPU and the dedicated CPU 8B exists, routing and the
  status route now skip the GPU Ollama catalogue entirely. The GUI can still
  show CPU-capable chat models, and a pinned 14B chat continues through its
  paired 8B CPU fallback.
- While the GPU is occupied, the **new-chat picker** now offers only actual
  CPU chat choices. It no longer presents a shared-store 14B entry that the
  router would correctly downgrade to 8B anyway.
- Corrected the dynamic GUI footer message: it now says that desktop chats can
  start a guarded general render and phone chats cannot. The previous dynamic
  message incorrectly claimed that no render could be started.

## Why

The initial baseline loaded and ran the exact 14B model, but its strict
completion field was false. The prior report only stored a hash, so it could not
distinguish whitespace or optional reasoning behavior from a genuine answer
failure. A cache benchmark must test a fixed completion, not accidentally
measure a reasoning stream.

## Evidence

The corrected baseline report
`ollama_kv_cache_baseline_f16_think_disabled_2026-08-25.json` completed its
fixed answer exactly with 10,676 prompt-evaluation tokens, 42.248 decode
tokens/s, and 11,859 MB resident VRAM. It was a model swap from the resident
8B, so its 52.139-second load time is not a fair cold-start comparison.

The explicitly opted-in candidate report
`ollama_kv_cache_flash_q8_2026-08-25.json` also completed exactly with the
same 10,676 prompt tokens, 73.300 decode tokens/s, and 10,361 MB resident
VRAM. That is 1,498 MB (12.6%) less resident VRAM in this observed run.

These are encouraging measurements, **not** a rollout decision: the two runs
did not begin from equivalent service/model state. The baseline launch remains
the default until a matched, idle-GPU comparison is recorded.

## Verification

- `python local_agent/test_measure_ollama_kv_cache.py` passes after the probe
  correction.
- `python local_agent/test_launcher_kv_cache.py` verifies the cache candidate
  is opt-in and GPU-only.
- `python local_agent/test_status_cache.py` verifies the GUI status probe is
  bounded during the cache window and refreshes after it.
- Router tests cover the no-GPU-inventory rule during an active render.
- `python -m unittest discover -s local_agent -p 'test_*.py'` — 148 passed.
- `python local_agent/agentic_eval.py` — 5/5 mocked harness checks passed.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`
  — 124/124 valid.

## Still unverified

- A matched cold/idle baseline-versus-Flash+q8 comparison remains outstanding.
  It requires ComfyUI to be deliberately stopped and the GPU explicitly made
  available; it will not be run or enabled automatically.
