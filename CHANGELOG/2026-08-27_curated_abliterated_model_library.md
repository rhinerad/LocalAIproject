# 2026-08-27 — Curated abliterated offline model library

## What changed

- Added `local_agent/download_curated_abliterated_library.py`.
- The downloader is intentionally an archive tool: it downloads exactly one
  GGUF per vetted model, writes a local manifest, resumes interrupted Hugging
  Face transfers, and does **not** import models into Ollama or load VRAM.
- Curated set:
  - Huihui Qwen3 30B-A3B Abliterated Q3_K_M (14.7 GB): constrained local-use candidate.
  - DeepSeek-R1-Distill-Qwen 32B Abliterated IQ4_XS (17.69 GB): CPU/partial-offload reasoning candidate.
  - DeepSeek-R1-Distill-Llama 70B Heretic Q4_K_M (39.60 GB): archive-only on this workstation.
  - GPT-OSS 120B Heretic Q4_K_M (87.9 GB): archive-only on this workstation; closest curated match to the requested 128B class.

## Guardrails

- No model is added to the chat picker merely because it has been downloaded.
- A model requires a separate compatibility, RAM/VRAM, and tool-calling test
  before it can be registered for Local Agent use.
- The 70B and 120B models are explicitly labeled archive-only for the current
  16 GB VRAM / 32 GB RAM workstation.

## Follow-up

- The 120B repository exposes its Q4_K_M quant as
  `gpt-oss-120b-heretic-GGUF-q4_k_m.gguf`; the downloader is pinned to that
  exact public filename after a pre-download repository listing check.
