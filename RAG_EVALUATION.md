# RAG evaluation — current state vs. Agentic RAG, 2026-09-02

## Status

This is a **gap analysis and proposal only.** Nothing in this document has
been implemented. Per `TODO.md`'s Phase 1 gate (engine architecture
evaluation, still open), no code from this proposal is to be written until
the Phase 1 milestone closes — see the corresponding blocked entry added to
`TODO.md`'s Phase 2 section.

## Research: state of the art, 2026

**Agentic RAG.** Modern agentic RAG systems are organized around four
capabilities: query understanding/planning, retrieval orchestration,
multi-hop reasoning/decomposition, and self-reflection. The core loop is
retrieve → reason → retrieve, repeated until the agent judges it has enough
evidence, with query rewriting/decomposition splitting a complex question
into sub-queries before retrieval. Reflection (the agent grading its own
retrieved context and retrying on insufficiency) measurably improves
citation accuracy but at real latency cost — not a free upgrade.

**Hybrid search + reranking.** The 2026 standard production pattern runs a
sparse retriever (BM25 or SPLADE) and a dense vector retriever in parallel,
merges results with Reciprocal Rank Fusion (RRF, which fuses by rank rather
than raw score — sparse and dense scores aren't on comparable scales), then
reranks the fused top-N (typically 50-200 candidates) with a cross-encoder,
which scores query+document jointly rather than independently the way
embedding similarity does. Published benchmarks show hybrid alone beats
either single method by ~7%, and hybrid+reranking pushes Recall@5 well past
hybrid alone.

## Audit: what this codebase actually has today

**The general-purpose local-docs RAG tool (`local_agent/retrieval.py`,
exposed as the `search_docs` tool) is lexical-only.** It is a from-scratch,
stdlib-only BM25 implementation (~35 lines, no `rank_bm25`, no `sklearn`) —
deliberately dependency-free, per its own docstring. There is no vector
search, no hybrid fusion, and no reranking in this path at all. Chunking
itself is reasonable (heading-aware splits with overlap), so the gap is in
scoring, not chunking.

Critically, this isn't an oversight the codebase is unaware of — **the
scorer is already built as a swappable interface for exactly this reason.**
`retrieval.py` defines a `ScorerProtocol`, `LexicalScorer` as the current
default, and an `EmbeddingScorer` class that exists **only as a stub**:

```python
class EmbeddingScorer:
    """Placeholder for UPGRADE 05 — plug in an embedding model without changing callers."""
    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        raise NotImplementedError("EmbeddingScorer requires an embedding model (UPGRADE 05)")
```

And there is a **written, unexecuted spec for filling that stub in**,
already in the repo: `local_agent/UPGRADE/05_models_after_internet.md`,
Job 2 ("real embeddings for retrieval") — pull `nomic-embed-text`, embed
each chunk once, cache vectors beside the index, embed the query per
search, rank by cosine similarity. This was gated on a one-time real
-internet download and appears to have been superseded by later
reprioritization before it was executed, not abandoned as a bad idea.

**Dense embeddings are not a research gap here — they're a proven, running
capability, just scoped to a different subsystem.** `local_agent/
exemplar_embeddings.py` is a real, working Chroma DB integration using the
exact same `nomic-embed-text` model, CPU-only (`num_gpu: 0`, four threads),
storing three collections (`exemplars_video_prompts`, `exemplars_comfyui`,
`exemplars_screenplay_beats`). This proves the local embedding pipeline
works end-to-end on this hardware — it's just wired to Equal Shares
creative-exemplar retrieval, not to general documentation/knowledge RAG or
conversational memory. Standing up `EmbeddingScorer` would reuse this exact
model and a near-identical Chroma pattern, not invent a new one.

**No hybrid fusion, no reranker, anywhere in the docs-retrieval path.**
Once `EmbeddingScorer` exists, nothing currently fuses its ranking with
`LexicalScorer`'s, and no cross-encoder or equivalent reranking step exists
in this codebase for text retrieval.

**No agentic loop (query rewriting, multi-hop, self-correction) wraps
`search_docs`.** `retrieval.search_relevant()` is the closest thing to
self-grading — its docstring explicitly calls it "a cheap, deterministic
document-grader layer for Self-RAG-style use" — but it filters by lexical
term overlap only and **explicitly does not call a second model** to judge
relevance ("intentionally does not invent a relevance score with a second
language model"). If a search returns nothing useful, the contract is that
the agent must say the local documents didn't establish the claim — there
is no automatic query rewrite or retry.

**However, the agentic-loop pattern itself already exists and works in this
codebase — just for a different retrieval source.** `local_agent/
deep_research.py` is a bounded, working multi-hop research orchestrator:
`MAX_ROUNDS = 4`, `MAX_SUBQUERIES = 5`, `MAX_SOURCES = 12`, routes through
`router.decide()` so a render still owns the GPU, and has the local model
plan sub-queries, retrieve, and synthesize — but it's wired to
`search_backend` (web search), not to `retrieval.py`/local docs. This is
directly reusable architecture for a local-docs agentic loop, not a
from-scratch design problem.

### Summary table

| Capability | State |
|---|---|
| Lexical (BM25) search | Implemented, working (`retrieval.py`) |
| Dense/vector search over docs | Not implemented — stubbed (`EmbeddingScorer`), spec already written (UPGRADE 05 Job 2) |
| Dense embeddings generally | Proven and running, scoped to exemplar retrieval only (`exemplar_embeddings.py`) |
| Hybrid fusion (RRF or similar) | Not implemented |
| Cross-encoder reranking | Not implemented |
| Query rewriting / decomposition over docs | Not implemented |
| Multi-hop retrieve-reason-retrieve over docs | Not implemented, but the pattern is proven elsewhere (`deep_research.py`, web-scoped) |
| Self-correction / relevance grading | Deterministic lexical-overlap filter only, explicitly not model-judged (`search_relevant`) |

## Gap analysis

The honest framing: this is not "no RAG, build from zero." It's **basic,
working lexical RAG, with every major missing piece already either
stubbed with a named upgrade path, proven elsewhere in the same codebase
with the same model, or both.** The three real gaps against 2026 Agentic
RAG practice are:

1. **No dense retrieval in the docs path** — despite the model and a
   working Chroma pattern already existing one file away.
2. **No hybrid fusion or reranking** — even after dense retrieval exists,
   nothing merges it with lexical results or reranks the merged set.
3. **No agentic loop (decomposition/self-correction) over local docs** —
   despite a bounded, working version of exactly this pattern existing for
   web research.

This matters for hallucination prevention specifically because
`search_relevant()`'s current contract — "empty result means the agent must
say the local documents did not establish the claim" — is a good safety
property that a dense/hybrid upgrade must preserve, not weaken. A denser
retriever that returns confident-looking-but-wrong chunks without a
grading step would be a regression, not an upgrade, if it's not paired with
reranking or self-correction.

## Proposal — staged, local-first, CPU-only where the existing pattern is

Consistent with this project's own gating discipline elsewhere (PowerInfer,
worker farm): staged, each stage's output evidence-preserved, nothing
auto-wired into production without review. All stages below are CPU-only —
`nomic-embed-text` already runs on the CPU endpoint (`num_gpu: 0`) for
exemplars, so this upgrade does not compete with the RTX 5080 for VRAM,
independent of whichever engine Phase 1 picks.

**Stage 1 — implement `EmbeddingScorer`, finish UPGRADE 05 Job 2 as
written.** Embed each chunk once (cache vectors beside `retrieval_index.
json`, same pattern as the existing index cache/lock), embed the query per
search, score by cosine similarity. Reuse `nomic-embed-text` via the same
CPU-only Ollama call pattern `exemplar_embeddings.py` already uses — do not
invent a second embedding call convention.

**Stage 2 — hybrid fusion.** Run `LexicalScorer` and the new
`EmbeddingScorer` over the same chunk set, merge with Reciprocal Rank
Fusion (rank-based, avoids the BM25-vs-cosine scale mismatch), expose as a
new `HybridScorer` behind the existing `ScorerProtocol` — no caller changes
needed, matching the interface's original design intent.

**Stage 3 — reranking.** Take the fused top-N (candidate: top 20-50, tuned
against this doc corpus's actual size) and rerank with a small local
cross-encoder. Needs a model decision (a compact cross-encoder that runs
CPU-only in reasonable latency) — flagged as an open question, not decided
here.

**Stage 4 — agentic loop over local docs.** Extend or parallel-build a
`deep_research.py`-style bounded orchestrator (same `MAX_ROUNDS`/
`MAX_SUBQUERIES`-style caps, same `router.decide()` GPU-ownership
discipline) scoped to `search_docs` instead of `search_backend`: decompose
a complex question into sub-queries, retrieve per sub-query, and use an
explicit model-graded relevance check (a real Self-RAG-style judge call,
replacing/augmenting `search_relevant`'s current lexical-only filter) to
decide whether to retry with a rewritten query or answer. Preserve the
existing "say so if local docs don't establish the claim" contract as the
fallback when the loop exhausts its bound.

**Stage 5 — quality comparison.** Cheap bar **2026-09-02ab** (mocked 2/2
vs 1/2; fail-closed top-5 matched Lexical on three queries) plus a
hand-judged 18-query fixture **2026-09-03aj**:
`local_agent/evaluations/retrieval_hand_judged.json`. Fail-closed Hybrid
(CPU embed down): **13/18 in top-5**. Live-dense Hybrid **2026-09-03bb**
(nomic-embed-text on CPU `:11435`): still **13/18 top-5**, search_docs
gold **13/18 vs lexical 12/18**, mixed not a clear win — Hybrid recovers
three paraphrases and drops two lexical already had in top-2. Default
stays Hybrid. Hybrid is **inert until CPU Ollama `:11435` is brought up
deliberately** (eval instance stopped 2026-09-03bf; fail-closes to
lexical). The two regressions (`phase1_stay_on_ollama` 1→9,
`judge_not_registered` losing the NotRegistered root-cause section)
must be addressed before dense embedding is a production decision —
not averaged away by the net +1 gold. Packet:
`local_agent/evaluations/retrieval_human_side_by_side.md`. See
`CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md` and
`CHANGELOG/2026-09-03bf_cpu_ollama_11435_stopped_fail_closed.md`.

## Open questions

1. ~~Cross-encoder model choice for Stage 3~~ — **researched 2026-09-02;
   re-evaluated 2026-09-03ae as a close call, nothing installed.**
   FlashRank catalog options are `ms-marco-TinyBERT-L-2-v2` (default) and
   `ms-marco-MiniLM-L-12-v2` (larger). `ms-marco-MiniLM-L-6-v2` is not in
   FlashRank's catalog. onnxruntime 1.29.0 is already present via chromadb,
   so the old "new native runtime" gate is stale; remaining costs are
   FlashRank + TinyBERT (~5 MB) + ~510 MiB Ranker RSS, 61% chunk truncation
   at 2000 chars, and unmeasured lift over Hybrid (TinyBERT is ~+3 nDCG@5
   vs BM25, not vs hybrid RRF). Stage 4 already gives a HybridScorer-backed
   judged path via `agentic_search_docs`. Default stays Hybrid. Hand-judged
   18-query fixture (2026-09-03aj / 2026-09-03bb) shows fail-closed Hybrid
   13/18 top-5; live-dense Hybrid still 13/18 with mixed search_docs
   usefulness vs lexical (13 vs 12 gold; two lexical wins). See
   `CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md`.
2. ~~Whether Stage 4's agentic loop shares code with `deep_research.py`~~ —
   **resolved during implementation, 2026-09-02:** it mirrors
   `deep_research.py`'s structure and conventions closely (same
   `_reason()`/`router.decide()` pattern, same dependency-injection test
   style, same untrusted-evidence prompt framing) but is a separate module
   (`agentic_retrieval.py`), not shared code — `deep_research.py` is
   web-scoped and file-writes/state assumptions differ enough that a shared
   implementation wasn't a clean fit. See
   `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md`.
3. Whether this work happens before or after Phase 1's TinyChatEngine/
   PowerInfer decision closes — **moot as of 2026-09-02: Phase 1 closed**
   (operator decision: stay on Ollama with current models). Stages 1, 2, 4,
   and 5 (cheap comparison + Hybrid default) are done; Stage 3 was
   re-evaluated 2026-09-03ae as a close call (not a clear win) and left
   unimplemented. See `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md`.
