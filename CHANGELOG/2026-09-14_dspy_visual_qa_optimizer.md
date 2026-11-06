# 2026-09-14 - DSPy optimizer against media_accuracy_gate

Scope: add a programmatic prompt-optimization loop for ComfyUI stills that
scores against the existing fail-closed visual QA gate. No Equal Shares
production, no router changes, no process kills, no live compile.

## Why

The supervisor conversational loop (read failure logs, rewrite prompt, retry)
does not scale. `media_accuracy_gate.py` already returns a binary mechanical
status plus a structured VLM verdict (`pass`, `rationale`, `observed`, seven
boolean `checks`). That is a DSPy metric, not a chat.

## Added

- `local_agent/comfy_api.py` — HTTP `POST /prompt` wrapper with isolated
  SaveImage prefix `dspy_opt/<stem>`. Does not use `tools.comfy_generate`
  (MCP hardcodes prefix `ComfyUI`). Does not start or kill ComfyUI.
  Defaults: RealVisXL, 1024x768 (4:3), `dpmpp_2m_sde` / karras.
  `POST /free` unloads Comfy models before the VLM so a 16 GB card can
  timeshare. Optional LoRA only when `DSPY_OPT_LORA` names a real file.
- `local_agent/dspy_optimizer.py` — DSPy signature/module, GEPA metric
  returning `dspy.Prediction(score, feedback)`, MIPROv2 scalar metric,
  render+VLM cache (GEPA calls the metric twice per example), SpaceXAI
  `dspy.LM(openai/grok-4.6, api_base=https://api.x.ai/v1)`. Seed is
  example-scoped, not optimized. `--compile` required to start a run.
- `local_agent/test_comfy_api.py`, `local_agent/test_dspy_optimizer.py`.

Unchanged: `media_accuracy_gate.py` (metric consumes it; does not fork it).

## Not done (operator)

- `pip install dspy` in the overnight Python.
- `XAI_API_KEY` for compile.
- Live Rockernow on :8188 and exact Qwen2.5-VL Caption V4 llama.cpp on :11436.
- A real JSONL trainset; the baked default is three assertion-passing plates
  from `test_media_accuracy_gate.py`, not the production pack.

## Validation

```
python -m py_compile local_agent/comfy_api.py local_agent/dspy_optimizer.py
  local_agent/test_comfy_api.py local_agent/test_dspy_optimizer.py
python -m unittest local_agent.test_comfy_api local_agent.test_dspy_optimizer
  local_agent.test_media_accuracy_gate -q
```

41 passed (CPU-only; no ComfyUI, no VLM load, no `dspy` install required for tests).
Live `--compile` was not run: `dspy` is not installed in this Python, and a
compile needs Rockernow :8188 plus Caption V4 llama.cpp :11436 plus `XAI_API_KEY`.
