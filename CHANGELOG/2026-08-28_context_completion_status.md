# 2026-08-28 — Context feature completion status

## Verified

- `test_context_compactor.py`: 3/3 passed.
- `test_memory_extractor.py`: 3/3 passed.
- `test_context_resilience.py`: 5/5 assertions passed.
- `test_prompt_prefix.py`: 2/2 passed.
- `test_artifacts.py`: 3/3 passed.
- `test_router_switching.py`: 27/27 passed.

## Remaining external prerequisite

The implementation intentionally requires the exact `llama3.1:8b` model on
the CPU-only Ollama server (`127.0.0.1:11435`) for live LLM compaction and
post-turn memory extraction. The model was not present. An attempted pull was
blocked by the managed Codex environment before it reached the Ollama registry.
No fallback model was substituted; deterministic trimming remains active and
memory extraction stays disabled until the exact helper model is installed.

Run this from a normal local PowerShell session, outside managed Codex network
restrictions, to complete both checklist items:

```powershell
$env:OLLAMA_HOST = '127.0.0.1:11435'
ollama pull llama3.1:8b
```

## Curated offline library status

- Completed: Qwen3 30B-A3B Abliterated Q3_K_M (14.7 GB), DeepSeek-R1-Distill-
  Qwen 32B Abliterated IQ4_XS (17.69 GB), and DeepSeek-R1-Distill-Llama 70B
  Heretic Q4_K_M (39.60 GB).
- Paused: GPT-OSS 120B Heretic Q4_K_M archive download, using the verified
  repository filename `gpt-oss-120b-heretic-GGUF-q4_k_m.gguf`. A 31 GB
  resumable partial is preserved; the transfer was paused after repeated
  no-progress, high-RAM Xet stalls in the managed environment.
- None of these archive downloads changes the active Local Agent chat model,
  registers a picker entry, starts a server, or loads GPU memory.

## Transfer recovery

### Current state

- Standard HTTP recovered a real 31 GB partial, but Hugging Face requires the
  Xet helper to finish a file at this size. The helper again stalled without
  adding bytes, so the process was paused rather than left consuming memory.
- Resume it from a normal non-sandboxed terminal with:

  ```powershell
  python .\local_agent\download_curated_abliterated_library.py --download --only gpt_oss_120b_heretic
  ```

- The initial GPT-OSS 120B Xet transfer made no disk progress while retaining
  approximately 1.3 GB RAM. Its verified downloader process was stopped; the
  partial-download metadata was retained. The downloader now exposes an
  explicit `--disable-xet` option for this host, which uses Hugging Face's
  ordinary resumable HTTP transfer if Xet stalls before writing bytes.
