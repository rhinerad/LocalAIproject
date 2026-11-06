# Enforce abliterated-only model policy across all agent tiers

**Date:** 2026-08-23  
**Revision bump:** r14 → r15

## Policy

All AI models used by the local agent must be abliterated variants.
huihui_ai (Ollama) is the canonical source. No stock, fine-tuned-uncensored,
or non-abliterated models in any model list.

## Changes

### `local_agent/router.py`

**CPU_MODELS** — removed: `qwen3:8b`, `dolphin3:latest`, `qwen2.5-coder:7b`,
`qwen2.5:7b`, `llama3.1:8b`, `qwen2.5-coder:14b`.
Replaced with: `huihui_ai/qwen2.5-coder-abliterate:7b`,
`huihui_ai/qwen2.5-abliterate:7b`, `huihui_ai/qwen2.5-coder-abliterate:14b`.

**GPU_MODELS** — removed: `qwen3:8b`, `qwen2.5-coder:14b`, `qwen3.6:latest`,
`dolphin3:latest`, `qwen2.5-coder:32b`, `qwen2.5:32b`, `qwen2.5:14b`,
`llama3.1:8b`.
Replaced with: `huihui_ai/qwen3.6-abliterated:27b`,
`huihui_ai/qwen2.5-coder-abliterate:32b`, `huihui_ai/qwen2.5-abliterate:32b`,
`huihui_ai/qwen2.5-abliterate:14b`, `huihui_ai/qwen2.5-coder-abliterate:14b`.

Note: The primary and fallback reasoning models (`huihui_ai/qwen3-abliterated:14b`
and `huihui_ai/qwen3-abliterated:8b`) were already abliterated and unchanged.

### `local_agent/capabilities.py`

**Secondary vision tier** — removed: `llama3.2-vision:11b-vision-instruct-q8_0`,
`llama3.2-vision:11b`, `qwen2.5vl:4b`, `qwen2.5vl:3b`.
Replaced with: `huihui_ai/qwen2.5-vl-abliterated:7b`,
`huihui_ai/qwen2.5-vl-abliterated:3b`.

The abliterated models already at the top of each tier list (`huihui_ai/llama3.2-vision-abliterated:11b`,
`huihui_ai/qwen3-vl-abliterated:4b`) are unchanged.

### `local_agent/Modelfile.equal-shares`

`FROM qwen2.5-coder:14b` → `FROM huihui_ai/qwen2.5-coder-abliterate:14b`.
Recreate the local model after pulling the new base:
```
ollama pull huihui_ai/qwen2.5-coder-abliterate:14b
ollama create equal-shares -f local_agent\Modelfile.equal-shares
```

## Action model pull completed

`huihui_ai/qwen3-vl-abliterated:32b` pulled successfully (20 GB, Q4_K_M).
Confirmed capabilities: completion, vision, tools, thinking.
Native context: 262144 tokens.
