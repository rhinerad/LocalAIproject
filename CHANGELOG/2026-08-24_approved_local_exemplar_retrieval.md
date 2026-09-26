# 2026-08-24 — Approved local exemplar retrieval

## Approved installation

The operator explicitly approved the local-only install of:

- `chromadb==1.5.9` in the local-agent Python environment;
- Ollama `nomic-embed-text:latest` (274 MB).

No external corpus, model other than the approved embedding model, or render
asset was downloaded. Chroma anonymous telemetry is disabled in the local client.

## What changed

- Added CPU-only `ollama_client.embed()` using `num_gpu: 0`, four threads, and
  `keep_alive: 0`.
- Added `exemplar_embeddings.py`: three persistent local Chroma collections,
  approved-only embedding, cosine semantic duplicate refusal above 0.90, and a
  deferred background retry that never runs while a chat is streaming.
- Approval now embeds the approved record. Pending and rejected records cannot
  be embedded or retrieved.
- Applicable prompt/workflow/screenplay questions receive at most two
  source-and-license-labelled approved examples in a hard 800-token context cap.
- The retrieved IDs are stored only in assistant-turn metadata. A later explicit
  rating automatically updates those exemplars' lifecycle counters; raw chat
  content is still not made into training data.

## Verification

- Local CPU Ollama `/api/embed` returned a 768-dimensional nomic vector.
- Chroma upsert/query smoke check passed.
- Full local-agent suite: **112 tests passed**.
- Agentic harness baseline: **5/5 passed** (mocked; no model loaded).
- `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.
