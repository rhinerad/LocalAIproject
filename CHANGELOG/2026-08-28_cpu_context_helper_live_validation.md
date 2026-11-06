# 2026-08-28 — CPU context-helper installation and live validation

## Installed

`llama3.1:8b` was downloaded to the dedicated Ollama CPU host at
`127.0.0.1:11435`. It is configured only for context compaction and
post-turn memory extraction, with `num_gpu=0`, four CPU threads, and
`keep_alive="0"`. It is not a chat-model fallback and is never routed to the
GPU.

## Verified

- A controlled `context_compactor.summarize_old_messages()` call returned the
  required strict JSON structure.
- A sensitive-input `memory_extractor.extract_and_remember()` call returned an
  empty result and wrote no durable fact.
- `ollama ps` was empty after each check; GPU utilization remained 0%.
- `test_context_compactor.py`, `test_memory_extractor.py`, and
  `test_context_resilience.py` passed. The resilience test now mocks the
  compactor boundary so normal regression runs cannot load an LLM.

## Safety

The CPU server exists independently of the GPU Ollama server. No ComfyUI
process, render, or vision model was started during installation or validation.

## Tracker

The project tracker now marks Context Pillars 1 and 3 complete. All four
context/token pillars and the VRAM-eviction correction are complete.
