# 2026-09-03ae — RAG Stage 3 FlashRank close-call (not implemented)

Re-read live `local_agent/retrieval.py` and the Phase 2 / Stage 3 outline
(`TODO.md` item 4, `RAG_EVALUATION.md`, `docs/hybrid_scorer_proposal.md`).
Did not treat 2026-09-02m / 2026-09-02ab as current state.

**Decision: not a clear win. Keep `HybridScorer` as `_DEFAULT_SCORER`.
Do not pip-install FlashRank. Do not add `RerankedScorer`.**

## What is true on disk today

- `_DEFAULT_SCORER = HybridScorer()` (RRF of stdlib BM25 + CPU
  `nomic-embed-text`). Empty still means "local docs don't establish the
  claim." Embedding failures fall back to lexical-only.
- Stage 3 is still a sketched opt-in wrap (`RerankedScorer` over Hybrid's
  fused top-N 20–50), not code. FlashRank is not imported anywhere.
- `search_docs` stays in `CONCURRENCY_SAFE_TOOLS`. Judged/cited answers
  already go through Stage 4 `agentic_search_docs` (model-graded retry).
- Index (2026-09-03T07:17:36Z): **404 files, 940 chunks**, 4.4 MB.
  Median chunk **2299 chars**; **577 / 940 (61%) over 2000 chars**
  (the proposal's `RERANK_CHARS`). TinyBERT pairwise max is 512 tokens.
- Embedding cache exists but holds **2 vectors**. The dense side of Hybrid
  is not populated for this corpus; first live `search_docs` would embed.
- Workstation Python 3.12.10: **flashrank not installed**. **onnxruntime
  1.29.0 is already installed** (43.1 MB on disk, pulled by `chromadb`
  for exemplar retrieval). `tokenizers`, `numpy`, `requests`, `tqdm`
  are already present. `torch` is not.

The 2026-09-02ab "new onnxruntime runtime, same bar as PowerInfer" reason
is **stale for this interpreter**. The remaining costs are FlashRank itself
(~14 KB wheel), the TinyBERT ONNX (~5 MB), Ranker RSS, truncation, and
unmeasured quality on *this* corpus.

## Accuracy (published, not this corpus)

There is still **no hand-judged local query set**. Stage 5 was a 2-query
mocked fixture (Hybrid 2/2 vs Lexical 1/2) plus lexical fallback matching
on three on-disk queries. That does not measure a cross-encoder.

What published numbers actually say for the catalog default
`ms-marco-TinyBERT-L-2-v2` (not L-6-v2 — still not in FlashRank's catalog):

- BEIR, rerank BM25 top-100 (Sentence-Transformers table): TinyBERT-L-2-v2
  MSMARCO nDCG 0.354 vs MiniLM-L-6-v2 0.401 / MiniLM-L-12-v2 0.401. TinyBERT
  is the fast/small option, not the quality option.
- FutureQueryEval (arxiv 2508.16757): BM25 nDCG@5 **43.01** → FlashRank
  TinyBERT-L-2-v2 **45.89** (+2.9) → MiniLM-L-12-v2 **51.72** (+8.7).
  Rank-1 lift for TinyBERT is larger (+5.8 nDCG@1) than @5.
- Those deltas are vs **BM25**, not vs hybrid RRF of BM25 + dense. Hybrid
  already recovered the one semantic miss in the Stage 5 fixture. Incremental
  lift of TinyBERT over Hybrid on a 940-chunk, jargon-heavy project tree
  is **unmeasured** and expected to be smaller than the BM25 deltas.
- 61% of local chunks exceed the 2000-char CE window. Heading-aware splits
  put useful text first, but a cross-encoder that never sees the back half
  of a 3000-char chunk can demote the right hit. That risk is specific to
  this indexer (`CHUNK_CHARS = 3000`) and is not in the generic BEIR tables.

A CE only reorders Hybrid's fused head. It cannot recover a chunk Hybrid
never put in top-N. Stage 4 already retries with rewritten queries when
evidence is weak.

## Latency and footprint

Proposal addendum (2026-09-03, throwaway venv, not this workstation):
TinyBERT-L-2-v2, `max_length=512`, 2000-char passages, N=20/50:
**~43 / ~95 ms** mean, peak RSS **~510 MiB**, disk **~5 MB**. Fine as extra
search latency; not fine as a silent ~0.5 GiB residency on a tool that is
in `CONCURRENCY_SAFE_TOOLS` (ONNX sessions are not automatically thread-safe).

Install if we did it: `pip install flashrank` (depends on onnxruntime,
already here) + first-use download of TinyBERT. No torch. MiniLM-L-12-v2
(~34 MB) is the catalog quality fallback and is several times slower.

## Why this stays a close call

For:

- onnxruntime / tokenizers are already on the workstation via chromadb,
  so the native-runtime intake is no longer "from zero."
- TinyBERT is cheap in disk and per-query time.
- Cross-encoders are the 2026 production last mile for web-scale RAG.

Against:

- Quality vs **this** HybridScorer is unmeasured. TinyBERT's published lift
  over BM25 is modest; MiniLM-L-12 is the one with a real gap, and that is
  the slower/heavier model the proposal said not to ship first.
- 61% of chunks would be truncated into the CE.
- Dense Hybrid is not even warm (2 cached vectors).
- Stage 4 already covers judged answers without a new package.
- `search_docs` concurrency contract vs ~510 MiB Ranker + ONNX.
- Adding dead `RerankedScorer` scaffolding with mocked tests would not
  improve accuracy; installing FlashRank "to see" would be guessing.

Not a clear win. Implementing would be guessing. Default stays Hybrid.
Revisit only with a hand-judged local query set that shows Hybrid ranking
the right chunk outside top-5, or an explicit operator approval that names
`flashrank` + TinyBERT (or MiniLM-L-12) and accepts RSS / truncation.

## Not done

No `pip install`, no model download, no `retrieval.py` edit, no default
flip, no farm/agent/worker_farm changes, no `APP_REVISION` bump, GUI not
started.

## Files

- `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md` (this)
- `TODO.md` Phase 2 item 4 Stage 3 note
- `RAG_EVALUATION.md` open question 1
- `docs/hybrid_scorer_proposal.md` 2026-09-03ae addendum
