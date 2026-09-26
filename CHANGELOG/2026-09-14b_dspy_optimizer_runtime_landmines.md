# 2026-09-14b - DSPy optimizer runtime landmines

Scope: refactor `local_agent/dspy_optimizer.py` and `local_agent/comfy_api.py`
after an overnight-runtime audit. No Equal Shares production, no live compile.

## Three failures acknowledged

1. **DSPy OutputField hyperparameters.** `cfg` / `steps` / `sampler` as
   signature strings will eventually emit `"around 30"` and crash integer
   casts. They are removed from the signature and locked at cfg=7.0,
   steps=30, sampler=euler in the execution wrapper.
2. **History poll hang.** A dropped ComfyUI prompt never appears in
   `/history`. Polling now has a strict 60s wall-clock cap and raises
   `TimeoutError`.
3. **VRAM death spiral.** `POST /free` unloads ComfyUI only. Caption V4
   llama-server keeps its allocation after the HTTP response. Mechanical
   failures never load the VLM. After a VLM call the harness offloads
   llama-server (`release_qwen25_vl_runtime`, then the :11436 listener if
   still resident) so iteration 2 can load SDXL.

## Wiring notes vs the audit snippet

The snippet's control flow is what landed. These live-API facts from
`media_accuracy_gate.py` / `media_tools.py` were not copied blindly:

- assertion key is `pass`, not `passed`
- `semantic_verdict_from_caption(caption, prompt, *, model, runtime)`
- `_run_vision_gpu` takes `[Path], question, model, host, instruction=...`
- checks live on `verdict["checks"]`

## Validation

```
python -m py_compile local_agent/comfy_api.py local_agent/dspy_optimizer.py
  local_agent/test_comfy_api.py local_agent/test_dspy_optimizer.py
python -m unittest local_agent.test_comfy_api local_agent.test_dspy_optimizer
  local_agent.test_media_accuracy_gate -q
```

45 passed (CPU-only; no ComfyUI, no VLM load). Live `--compile` was not run.
