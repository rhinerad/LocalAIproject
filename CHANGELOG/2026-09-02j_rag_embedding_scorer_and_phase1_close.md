# 2026-09-02 — Phase 1 milestone closed; RAG Stages 1-2 implemented

## Scope

Two things happened in one turn, in this order: (1) operator explicitly
overrode the Phase 1 gate for the RAG upgrade item specifically, then in
the same reply gave the actual engine decision that closes Phase 1
("continue to use the models we already have — Qwen models, gpt-oss");
(2) `EmbeddingScorer`/`HybridScorer` (RAG_EVALUATION.md Stages 1-2) were
implemented in `local_agent/retrieval.py`.

## Phase 1 milestone — closed

`TODO.md`'s Phase 1 milestone checkbox is now checked. Operator decision:
stay on Ollama with the current models (Qwen family, `gpt-oss`). No
PowerInfer route (TurboSparse calibration completion, Bamboo-DPO
prompt-contract resolution) and no TinyChatEngine intake are being pursued
at this time. This isn't a technical rejection of either — it's closing the
evaluation with "not now": ReluLLaMA-7B (PowerInfer's only benchmarked
candidate) already failed its quality gate, TurboSparse/Bamboo-DPO both
have unresolved prerequisites, and TinyChatEngine's CUDA path is narrow and
carries unverified `sm_120` risk. All of that stays on file if revisited.

`TODO.md`'s Phase 2 header changed from "BLOCKED by Phase 1" to "was
BLOCKED, now unblocked" with a note that item 4 (RAG upgrade) was actually
implemented moments before this closure, under an explicit override, not
after — recorded so the sequence isn't misread later.

## RAG upgrade — Stages 1 and 2 implemented

`local_agent/retrieval.py`:
- **`EmbeddingScorer`** replaces the `NotImplementedError` stub. Real dense
  retrieval via the CPU-only `nomic-embed-text` Ollama endpoint — same
  model, host (`router.CPU_HOST`), and `keep_alive="0"` convention already
  proven by `exemplar_embeddings.py`. Vectors cached at
  `knowledge/retrieval_embeddings.json`, keyed by chunk id and validated by
  a SHA-1 hash of the chunk's own text, so editing one part of a doc only
  re-embeds the chunks that actually changed.
- **`HybridScorer`** fuses `LexicalScorer` (BM25) and `EmbeddingScorer` via
  Reciprocal Rank Fusion (RRF, `k=60`, standard constant) — rank-based
  because BM25 and cosine scores aren't on a comparable scale. Only chunks
  clearing a relevance bar from either side (BM25 > 0, or cosine ≥
  `MIN_EMBED_SIMILARITY = 0.35`) enter the fused pool; this was a
  deliberate correctness fix during implementation — naive RRF over the
  full chunk set would never return empty (RRF scores are positive for
  anything in the pool), which would have silently broken the existing
  "empty result means local docs don't establish this" safety contract
  that `search_relevant()` depends on. Falls back to lexical-only ranking
  if the embedding call raises (Ollama down, model not pulled), so
  `search_docs` keeps working fully offline as its docstring promises.
- **Neither is the default.** `search()`/`search_docs` still default to
  `LexicalScorer` unless a caller passes `scorer=retrieval.HybridScorer()`
  explicitly. `search_relevant()` (the downstream grader used by
  `search_docs`) is still lexical-term-overlap-only — swapping the default
  without updating that grader (Stage 4, not done) would either discard
  genuinely relevant semantic hits or, if the grader were removed instead,
  let ungrounded matches through unfiltered. Flagged explicitly rather than
  silently left as a loose end.
- `MIN_EMBED_SIMILARITY = 0.35` is a heuristic, not measured against this
  corpus — flagged in-code and in `TODO.md` for revisit once there's real
  query traffic to tune against.

New file `local_agent/test_retrieval_embeddings.py` — 9 tests: embedding +
ranking by cosine similarity, cache reuse on unchanged chunks, cache
invalidation on edited chunk text (same id, new hash), hybrid fusion,
below-threshold exclusion on both sides, fallback to lexical-only on a
simulated Ollama outage, and `search()` accepting an explicit
`HybridScorer`. All Ollama calls mocked (`unittest.mock.patch
("ollama_client.embed", ...)`) — no real embedding call, no GPU, no network.

## Verification — honest gap

**Tests were written but not executed.** `mcp__workspace__bash` returned
"Permission denied" for this session/folder, so there was no way to
actually run `python -m unittest` or `py_compile` here. The full file was
re-read end to end and every test's mock call sequence was manually traced
against the implementation (embed call counts, cosine values, RRF pool
membership, exception fallback path) to check for logic errors, but that is
not the same as a real test run and is documented as such, per this
project's own rule that document/logic consistency is not verification.
**Before this code is trusted or wired into anything else, run:**
```
python -m py_compile local_agent/retrieval.py local_agent/test_retrieval_embeddings.py
python -m unittest local_agent.test_retrieval_embeddings -v
```

## What was not done

Stage 3 (cross-encoder reranking — model choice still unresearched), Stage
4 (agentic self-correction loop over `search_docs`, which is what actually
addresses the "no retry on empty search" gap originally flagged as the
biggest weakness — Stages 1-2 improve the retriever, not the correction
loop), and Stage 5 (human quality comparison before any default change) are
all still open, tracked in `TODO.md`. No GPU was used (embeddings are
CPU-only by design, same as exemplar retrieval). No existing behavior of
`search_docs` changed, since the new scorers aren't wired as default.
