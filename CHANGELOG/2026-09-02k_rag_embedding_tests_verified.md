# 2026-09-02 — retrieval embedding tests actually run: 7/7 pass

## Scope

Follow-up to `2026-09-02j_rag_embedding_scorer_and_phase1_close.md`, which
implemented `EmbeddingScorer`/`HybridScorer` but could only verify the new
tests by manual trace-through (`mcp__workspace__bash` was denied in-session).
The operator ran the suite directly.

## What was verified

```
PS ...\COMFYUI_STORY_HANDOFF_2026-08-09> python -m unittest local_agent.test_retrieval_embeddings -v
```
run from the repository root (the first attempt, from `A:\Users\rhine`,
failed with `ModuleNotFoundError: No module named 'local_agent'` — working
directory, not a code bug).

Result: **7 tests, all passed** — `test_embeds_and_ranks_by_cosine_similarity`,
`test_caches_vectors_and_does_not_re_embed_unchanged_chunks`,
`test_edited_chunk_text_invalidates_its_own_cache_entry_only`,
`test_fuses_lexical_and_embedding_hits`,
`test_excludes_chunks_below_both_relevance_bars`,
`test_falls_back_to_lexical_only_when_embedding_endpoint_unavailable`,
`test_search_uses_hybrid_scorer_when_explicitly_passed`.

## Correction

The prior entry and `TODO.md` said "9 tests" — miscounted; it's 7. Fixed in
`TODO.md`.

## What this closes

The "verification still owed" flag from the prior CHANGELOG entry is
resolved for `EmbeddingScorer`/`HybridScorer` specifically: the code
imports cleanly and behaves as the manual trace-through predicted. This
does not change anything about Stages 3-5 (reranking, agentic
self-correction loop, human quality comparison before default) — all still
open, unimplemented, tracked in `TODO.md`.
