# Stage 3 — RerankedScorer (FlashRank) — implementation proposal

**Status: proposal only. 2026-09-03ae close-call — do not implement.
Keep HybridScorer as default.**

Research is done. This is a short handoff for another agent. Nothing here
authorizes installing packages, flipping `_DEFAULT_SCORER`, or editing
`local_agent/retrieval.py`. Stage 3 stays deferred until the operator names
the new dependency in an explicit approval.

## Current state (do not rewrite HybridScorer)

`local_agent/retrieval.py` already has Stages 1–2, and they are the default
as of `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md`:

- `LexicalScorer` — stdlib BM25
- `EmbeddingScorer` — cosine over CPU `nomic-embed-text`
- `HybridScorer` — Reciprocal Rank Fusion of the two. Only chunks that
  clear BM25 > 0 **or** cosine ≥ `MIN_EMBED_SIMILARITY` enter the pool, so
  empty still means "local docs don't establish the claim"
- `_DEFAULT_SCORER = HybridScorer()` — `search` / `search_docs` use it
  unless a caller passes another `ScorerProtocol`

FlashRank is Stage 3 via a **new** `RerankedScorer` that wraps Hybrid and
reorders the fused top-N. It is not a HybridScorer rewrite, not a second
fusion method, and not a default-path change. See `TODO.md` Phase 2 item 4
and `RAG_EVALUATION.md` Stage 3.

## What FlashRank is here

Cross-encoder retrieve-then-rerank of Hybrid's fused top-N. Query and
document are scored jointly (unlike `EmbeddingScorer`'s independent cosine).

- Package: `flashrank`, **pairwise only** (do not pull listwise / RankGPT
  models)
- New runtime dep: `onnxruntime`
- **No torch**, no `sentence-transformers`, no `transformers`

`CHANGELOG/2026-09-02ab_phase2_hybrid_default.md` already said no to this
dependency. That deferral stands until a new explicit approval.

## Models (correct the 2026-09-02m pick)

`CHANGELOG/2026-09-02m_rag_stage3_reranker_research.md` named
`ms-marco-MiniLM-L-6-v2` (~80 MB). **That model is not in the FlashRank
catalog** (PrithivirajDamodaran/FlashRank issue #26). Do **not** recommend
installing L-6-v2. Do not add a custom ONNX of it.

| Role | FlashRank id | Size | Notes |
|---|---|---|---|
| Default / first | `ms-marco-TinyBERT-L-2-v2` | ~4 MB | FlashRank's own default. Start here. |
| Quality fallback | `ms-marco-MiniLM-L-12-v2` | ~34 MB | Pairwise catalog model. Opt-in only if TinyBERT quality is insufficient. |

Do not ship L-12 as the first install.

## Sketch — wrap Hybrid, do not flip the default

Same `ScorerProtocol.score(query, chunks) -> list[tuple[float, dict]]`.
Wrap an inner Hybrid; do not rewrite it.

```python
class RerankedScorer:
    """Stage 3: cross-encoder reorder of HybridScorer's fused top-N.

    Opt-in only. Do not assign to `_DEFAULT_SCORER`.
    """
    TOP_N = 50           # clamp 20–50; start at 50, tune down
    MODEL = "ms-marco-TinyBERT-L-2-v2"
    RERANK_CHARS = 2000  # under 512-token CE max; CHUNK_CHARS is 3000

    def __init__(self, inner: ScorerProtocol | None = None, top_n: int = TOP_N):
        self.inner = inner or HybridScorer()
        self.top_n = max(20, min(50, top_n))
        self._ranker = None  # lazy

    def _ranker_or_none(self):
        if self._ranker is not None:
            return self._ranker
        try:
            from flashrank import Ranker
        except ImportError:
            return None
        self._ranker = Ranker(model_name=self.MODEL, max_length=512)
        return self._ranker

    def score(self, query: str, chunks: list[dict]) -> list[tuple[float, dict]]:
        fused = self.inner.score(query, chunks)
        if not fused:
            return []
        ranker = self._ranker_or_none()
        if ranker is None:
            return fused  # missing flashrank/onnxruntime → Hybrid order
        head, tail = fused[: self.top_n], fused[self.top_n:]
        from flashrank import RerankRequest
        passages = [
            {
                "id": i,
                "text": (ch.get("text") or "")[: self.RERANK_CHARS],
                "meta": ch,
            }
            for i, (_score, ch) in enumerate(head)
        ]
        reranked = ranker.rerank(RerankRequest(query=query, passages=passages))
        # CE scores replace RRF on the head only. Do not globally re-sort
        # with tail — the two scales are not comparable.
        out = [(float(item["score"]), item["meta"]) for item in reranked]
        out.extend(tail)
        return out
```

Notes for the implementing agent:

- Call `Ranker.rerank(RerankRequest)` — that is the pairwise FlashRank
  surface. Do not use listwise helpers.
- Lazy-import `flashrank` inside the class so `retrieval.py` still imports
  with no new packages installed.
- Fallback on `ImportError` (and treat ranker runtime errors the same way
  Hybrid treats a dead embedding endpoint): return the inner Hybrid
  ranking; do not fail `search_docs`.
- Preserve `_match_by` on the shallow-copied chunks Hybrid already tags.
  Do not mutate index chunks.
- **Do not flip `_DEFAULT_SCORER`.** Callers opt in:
  `search(q, scorer=RerankedScorer())`. `search_docs` stays Hybrid.
  A Stage 5-style comparison happens *before* any later default flip, same
  bar as 2026-09-02ab.

## Truncation

`CHUNK_CHARS = 3000` (~800 tokens). FlashRank pairwise CEs are 512-token
max (query + document). Passing a full chunk silently truncates inside
ONNX and can drop the relevant span. Truncate to `RERANK_CHARS`
(candidate 2000 chars, ~500 tokens so query+doc fits) **before** building
`RerankRequest` passages. Prefer the start of the chunk (heading-aware
splits already put useful text first). Do not change `CHUNK_CHARS` or the
indexer.

## Risks (why this is still gated)

1. **New `onnxruntime` dependency.** `2026-09-02ab` explicitly deferred
   FlashRank/onnxruntime as a new runtime intake, same bar as PowerInfer /
   TinyChatEngine. `retrieval.py`'s module docstring still promises the
   default path has no FlashRank/onnxruntime. Approval must name the
   packages (`flashrank` + `onnxruntime`) and the first model
   (`ms-marco-TinyBERT-L-2-v2` only).
2. **Per-query CPU.** The cross-encoder scores every (query, candidate)
   pair. Top-N of 20–50 × TinyBERT-L-2 is workstation-CPU-sized; L-12 is
   slower. Keep `search_docs` on `CONCURRENCY_SAFE_TOOLS` only while
   rerank stays off the default path. `agentic_search_docs` already calls
   a model and is not concurrency-safe — do not silently hang a CE on
   that path either without approval.
3. **No farm rerank queue.** Embed and summarize already offload. There
   is no rerank Celery task and this proposal does not add one. If
   approved, rerank runs on **local workstation CPU only**. Do not touch
   `farm_offload.py`, `agent.py`, or `worker_farm/` files.

## Implementation steps (after approval only)

For another agent, in this order. Stop if approval did not name a step.

1. Record the approval in `TODO.md` Phase 2 item 4 Stage 3 (currently
   deferred) and a new `CHANGELOG/` letter — do not treat this proposal as
   that record.
2. Add `flashrank` + `onnxruntime` to the workstation agent env (not
   `worker_farm/.venv`). Confirm no torch pull. First model:
   TinyBERT-L-2-v2 (~4 MB). Do not install L-6-v2.
3. Add `RerankedScorer` to `local_agent/retrieval.py` as sketched. Do not
   change `HybridScorer`. Do not assign `_DEFAULT_SCORER`.
4. Tests in `local_agent/test_retrieval_embeddings.py` (or a sibling):
   wrap a fake inner scorer; mock `Ranker.rerank`; assert top-N reorder;
   assert `ImportError` returns inner order; assert chunks longer than
   `RERANK_CHARS` are truncated in the request, not in the index.
5. Opt-in call path only (`search(..., scorer=RerankedScorer())`). Leave
   `search_docs` / `agentic_search_docs` on Hybrid until a later
   Stage 5-style comparison.
6. Do not edit `farm_offload.py`, `agent.py`, or anything under
   `worker_farm/`.

## Do not implement until approved

This file is a design handoff. It does not install FlashRank, does not add
onnxruntime, does not flip the default scorer, and does not change
retrieval behavior. Stage 3 stays deferred per `TODO.md` Phase 2 item 4
and `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md` until the operator
explicitly approves the new dependency.

## Citations

- `local_agent/retrieval.py` — `ScorerProtocol`, `LexicalScorer`,
  `EmbeddingScorer`, `HybridScorer`, `_DEFAULT_SCORER`,
  `CHUNK_CHARS = 3000`
- `TODO.md` Phase 2 item 4 — Stage 3 deferred; intended `RerankedScorer`
  over Hybrid fused top-N (20–50)
- `RAG_EVALUATION.md` — Stage 3 rerank of fused top-N; open question
  closed then deferred
- `CHANGELOG/2026-09-02m_rag_stage3_reranker_research.md` — research-only;
  L-6-v2 pick is superseded by this doc (not in FlashRank catalog, issue
  #26)
- `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md` — Hybrid is default;
  FlashRank/onnxruntime explicitly not installed


## Addendum — TinyBERT local-CPU cost (2026-09-03)

Research-only. No package was added to the workstation agent env, and
`retrieval.py` was not edited. This bounds the "workstation-CPU-sized"
claim in Risks item 2 for the proposed default
`ms-marco-TinyBERT-L-2-v2` at fused top-N 20 and 50.

### Published numbers

- HuggingFace `cross-encoder/ms-marco-TinyBERT-L2-v2`: 4.39M params.
  Sentence-Transformers table: **9000 docs/sec on a V100 GPU**
  (NDCG@10 69.84, MRR@10 32.56). That is GPU, not CPU.
- FlashRank pairwise catalog: default id `ms-marco-TinyBERT-L-2-v2`,
  ~4 MB ONNX, no torch. README: speed is a function of passage tokens,
  query tokens, and layer count. Official CPU table is still **TBD**.
  The nano example constructs `Ranker(max_length=128)`.
- Third-party CPU claims for this same tiny CE (not always FlashRank
  Python):
  - Dixit, "Reranking in RAG" (Medium): FlashRank TinyBERT about
    **15–30 ms for N=50 on CPU**; a MiniLM cross-encoder 100–250 ms
    at the same N.
  - flashrank-js (`tiny` = `Xenova/ms-marco-TinyBERT-L-2-v2`) on a
    typical Windows x64 desktop, Node 24, CPU-only: load ~190 ms;
    median rerank **3 / 6 / 10 ms for 5 / 10 / 20 docs** (end-to-end,
    tokenization included, warmup excluded). Different runtime
    (transformers.js ONNX) than Python `flashrank`. Linear in N would
    put N=50 around 25 ms if the slope holds.

### Local dry-run (throwaway venv, dummy data)

`flashrank==0.2.10` + `onnxruntime==1.29.0`, Python 3.13.5.
API: `Ranker(model_name="ms-marco-TinyBERT-L-2-v2", max_length=...)`
then `ranker.rerank(RerankRequest(query=..., passages=...))`. No torch.
Cold download is a 3.26 MB zip; on-disk cache is **4.725 MiB**
(`flashrank-TinyBERT-L-2-v2.onnx` 4.28 MiB + tokenizer).

Host is **not** the workstation. Linux throwaway venv on a generic
Intel Xeon, 8 logical CPUs, 16 GiB RAM. Workstation for comparison:
AMD Ryzen 7 9800X3D (8C/16T, 4.7 GHz) + 32 GiB. Treat Xeon numbers as
a conservative ceiling, not a DuranGamingPC measurement.

**Short dummy passages** (`max_length=256`, ~70-word passages, 40
timed iters after 3 warmups):

| N | mean | p50 | p95 |
|---|---|---|---|
| 20 | 13.6 ms | 12.7 ms | 20.0 ms |
| 50 | 28.5 ms | 28.0 ms | 37.9 ms |

Cold load 815 ms (includes first download). Peak RSS ~153 MiB.

**Proposal-shaped passages** (sketch settings: `max_length=512`,
dummy passages exactly `RERANK_CHARS=2000` / ~283 words, 30 timed
iters, warm cache):

| N | mean | p50 | p95 | min | max |
|---|---|---|---|---|---|
| 20 | 43.4 ms | 42.1 ms | 59.7 ms | 31.0 ms | 62.6 ms |
| 50 | 95.0 ms | 94.9 ms | 105.4 ms | 76.6 ms | 128.3 ms |

Warm load ~100 ms. Peak RSS ~510 MiB. Pairwise tensor width was 455
tokens (attn nonzero ~448), not 512. FlashRank pads to the **batch
max**, not to `max_length`, so ONNX is not paying for 512-wide
padding on these inputs. Cost is ~linear in N (~1.9 ms per candidate
at this length on the Xeon).

Same 2000-char passages at `max_length=128` (FlashRank nano
example): ~20.6 ms / 40.6 ms for N=20/50, peak RSS ~167 MiB, but
sequences are **hard-truncated to 128 tokens**, which drops most of
a 2000-char chunk. Do not use 128 with `RERANK_CHARS=2000`.

### Estimate for the workstation

Nothing was installed on DuranGamingPC. A 9800X3D is a faster
desktop CPU than the Xeon used above. Expect **similar or better**
than the proposal-shaped run:

- **~40–100 ms** per query to rerank Hybrid's fused top-20–50 at
  `RERANK_CHARS=2000` / `max_length=512`
- **<600 MiB RSS** once loaded (peak on the Xeon was 510 MiB)
- **~5 MB disk** for the TinyBERT ONNX + tokenizer
- Cold start: one-time 3.3 MB download + ~0.1–1 s load; then lazy
  `Ranker` as sketched

That is inside a local `search()` budget and matches Risks item 2
("workstation-CPU-sized"). It does **not** change the onnxruntime
approval gate. Latency is not the reason Stage 3 stays deferred; the
new native runtime still is.

### What this does not measure

- Quality vs HybridScorer (RAG eval set, after approval only)
- `ms-marco-MiniLM-L-12-v2` (quality fallback; expect several times
  slower and more RAM)
- Concurrent `search_docs` while a CE is in-process
- Real index chunks vs dummy 2000-char English
- A measurement on the 9800X3D itself

### Citations (this addendum)

- https://huggingface.co/cross-encoder/ms-marco-TinyBERT-L2-v2
- https://github.com/PrithivirajDamodaran/FlashRank (v0.2.10;
  default model `ms-marco-TinyBERT-L-2-v2`; CPU bench TBD)
- https://medium.com/@vaibhav-p-dixit/reranking-in-rag-cross-encoders-cohere-rerank-flashrank-c7d40c685f6a
- https://github.com/zeeshan56656/flashrank-js (Windows x64 CPU
  medians for the same TinyBERT ONNX)


## Addendum — close-call decision (2026-09-03ae)

Re-read live `retrieval.py` (Hybrid is default; no FlashRank import).
**Not implemented.** Not a clear win over HybridScorer.

New facts vs 2026-09-02ab:

- Workstation Python 3.12.10 already has **onnxruntime 1.29.0** (43.1 MB,
  required-by chromadb) plus `tokenizers` / `numpy` / `requests` / `tqdm`.
  `flashrank` is still absent. The "new native runtime" gate is stale;
  remaining install is FlashRank (~14 KB) + TinyBERT ONNX (~5 MB).
- Live index: 940 chunks, median 2299 chars, **577/940 over 2000 chars**.
  `RERANK_CHARS=2000` would truncate 61% of this corpus into a 512-token CE.
- Embedding cache has 2 vectors. Hybrid's dense side is not warm.
- TinyBERT published lift is vs BM25 (~+2.9 nDCG@5 on FutureQueryEval);
  MiniLM-L-12 is ~+8.7. Neither is vs this Hybrid RRF. No local eval set.

Keep `_DEFAULT_SCORER = HybridScorer()`. Do not add `RerankedScorer`
until a hand-judged local query set or an explicit operator approval
that names the package and model. Evidence:
`CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md`.


## Addendum — hand-judged eval (2026-09-03aj)

Fixture: `local_agent/evaluations/retrieval_hand_judged.json` (18 queries).
Runner: `local_agent/eval_retrieval.py`. Fail-closed Hybrid (CPU `:11435`
down): **13/18 top-5**, **5 FlashRank-window misses**, **0 missing from
the pool**. Evidence:
`CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md`.


## Addendum — live-dense human comparison (2026-09-03bb)

nomic-embed-text on CPU `:11435` (Vulkan off; 5080 not used). Hybrid
search_docs gold **13/18** vs lexical **12/18**. Mixed: Hybrid recovers
`gpu_idle_but_cpu_8b` / `farm_embed_no_celery_import` /
`relullama_not_promotable`; lexical still wins `phase1_stay_on_ollama`
(hy rank 9) and `judge_not_registered` (hy rank 12). Not a clear win.
Default stays `HybridScorer`. FlashRank window still 5/18. Packet:
`local_agent/evaluations/retrieval_human_side_by_side.md`. Evidence:
`CHANGELOG/2026-09-03bb_retrieval_stage5_human_comparison.md`.

**Do not turn live dense on in production until the two lexical-win
regressions are understood.** They are not averaged away by the +1 gold:

- `phase1_stay_on_ollama` — “Did we stay on Ollama or switch to
  PowerInfer?” Lexical rank 1 is the Phase 1 close note. Hybrid rank 9;
  top-5 is older PowerInfer scaffold/pipeline/picker docs (the opposite
  implication).
- `judge_not_registered` — “Why did the first judge_transcript batch
  fail as NotRegistered?” Lexical rank 2 is the exact “Step 2 — root
  cause of NotRegistered” chunk. Hybrid rank 12; keeps the file intro
  and drops that section.

Until then Hybrid remains the code default but **inert**: workstation
CPU `:11435` is down (eval instance stopped 2026-09-03bf), query embed
fail-closes, ranking equals BM25. Starting `:11435` is its own decision.
See `docs/ARCHITECTURE.md` embed path and
`CHANGELOG/2026-09-03bf_cpu_ollama_11435_stopped_fail_closed.md`.
