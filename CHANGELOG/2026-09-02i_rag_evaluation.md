# 2026-09-02 — RAG evaluation: gap analysis + blocked upgrade proposal

## Scope

Operator-directed, explicit step-by-step task: research 2026 Agentic RAG /
hybrid-search-and-reranking practice, audit this codebase's actual
retrieval implementation, write `RAG_EVALUATION.md`, and add a new task to
`TODO.md`'s Phase 2 section explicitly marked BLOCKED by Phase 1 (engine
architecture). Documentation only — no retrieval code was written or
changed.

## What was done

**Research:** confirmed 2026 practice for agentic RAG (query
decomposition, multi-hop retrieve-reason-retrieve, self-reflection/
correction) and hybrid search (BM25/SPLADE + dense fused via Reciprocal
Rank Fusion, then cross-encoder reranking on the fused top-N).

**Audit, read directly from source:**
- `local_agent/retrieval.py` (the `search_docs` tool's backing
  implementation): pure stdlib BM25, no vector search. `EmbeddingScorer` is
  a literal `NotImplementedError` stub explicitly left for a named future
  upgrade.
- Found that upgrade is already specified, unexecuted:
  `local_agent/UPGRADE/05_models_after_internet.md`, Job 2 — pull
  `nomic-embed-text`, implement `EmbeddingScorer` by cosine similarity.
- Found working proof the embedding pipeline already runs on this hardware:
  `local_agent/exemplar_embeddings.py` — real Chroma DB + `nomic-embed-text`
  CPU-only (`num_gpu: 0`), three collections, scoped to creative-exemplar
  retrieval (video prompts, ComfyUI workflows, screenplay beats), not
  general docs/knowledge RAG.
- Found no hybrid fusion or reranking anywhere in the text-retrieval path.
- Found no agentic loop (query rewrite, multi-hop, model-graded
  self-correction) wrapping `search_docs`. `retrieval.search_relevant()` is
  a deterministic lexical-overlap filter, explicitly documented as *not*
  calling a second model to grade relevance.
- Found the agentic-loop pattern itself already proven elsewhere:
  `local_agent/deep_research.py` — a bounded (`MAX_ROUNDS=4`,
  `MAX_SUBQUERIES=5`), working multi-hop orchestrator, currently wired to
  web search (`search_backend`), not local docs.

## What was written

`RAG_EVALUATION.md` (project root): gap analysis table, a staged 5-stage
proposal (implement `EmbeddingScorer` → RRF hybrid fusion → cross-encoder
reranking → `deep_research.py`-style agentic loop over `search_docs` →
human quality comparison before any scorer change becomes default), all
CPU-only and largely engine-independent, with open questions flagged
(cross-encoder model choice, whether Stage 4 shares code with
`deep_research.py`).

`TODO.md`: added item 4 under `PHASE 2: Context & Memory Optimization —
BLOCKED by Phase 1`, explicitly marked blocked per operator instruction,
linking to `RAG_EVALUATION.md`. Renumbered the existing "Swarm offload"
item from 4 to 5 to keep the list sequential.

## Verification

Every specific claim in `RAG_EVALUATION.md` (the `EmbeddingScorer` stub,
the UPGRADE 05 Job 2 spec, the exemplar Chroma pipeline, `deep_research.py`'s
bound constants, `search_relevant`'s documented lexical-only behavior) is
sourced from directly reading the named file, not inferred or assumed.

## What was not done

No code was implemented. No `EmbeddingScorer`, no hybrid fusion, no
reranker, no agentic loop over local docs. No model was downloaded or run.
Per explicit operator instruction, this stays blocked until the Phase 1
milestone (still open — PowerInfer route and TinyChatEngine Stage 1
sign-off both pending) closes.
