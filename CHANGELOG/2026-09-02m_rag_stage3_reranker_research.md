# 2026-09-02 — RAG Stage 3: reranker research (no implementation)

## Scope

Resolved the "cross-encoder model choice" open question from
`RAG_EVALUATION.md` Stage 3. Research only — no package installed, no code
written, no dependency added.

## Finding

**FlashRank** — purpose-built for lightweight local CPU reranking,
ONNX-optimized, dependency-light by design — with the `ms-marco-MiniLM-L-6-v2`
reranking model (~80 MB) is the best-fit candidate for this project: small,
CPU-fast, no GPU requirement, no heavy ML framework (no full
`sentence-transformers`/`transformers`/PyTorch stack needed).

## Why not implemented now

This is a genuinely new runtime dependency (`onnxruntime` at minimum).
`local_agent/retrieval.py`'s own module docstring currently promises the
default path needs "nothing to install" and works fully offline forever —
adding a reranker doesn't touch that default (same non-default pattern as
`EmbeddingScorer`/`HybridScorer`), but this project has a consistent rule of
gating any new model/dependency intake behind an explicit decision (see the
PowerInfer and TinyChatEngine intake processes this session). Recorded in
`TODO.md` and `RAG_EVALUATION.md` as pending that decision, with the
intended design already sketched (a `RerankedScorer` taking `HybridScorer`'s
fused top-N and reordering by cross-encoder score, same
fall-back-gracefully discipline already used by `HybridScorer`).

## What's still open in the RAG upgrade

Stage 3 (this — pending dependency approval) and Stage 5 (human quality
comparison before any of Stages 1/2/4 becomes `search_docs`'s default
behavior — inherently needs the operator, not something to complete
unilaterally). Stages 1, 2, and 4 are implemented and test-verified
(15 tests total across `test_retrieval_embeddings.py` and
`test_agentic_retrieval.py`, all passing).
