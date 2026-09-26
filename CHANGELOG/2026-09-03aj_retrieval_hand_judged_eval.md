# 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal)

18 real questions this project has actually needed answered, each with
ground-truth chunk ids read from the live index. Re-runnable against any
future scorer. This is the Stage 5 set that 2026-09-02ab left as an
operator lever, and the measurement 2026-09-03ae said FlashRank needed
before a default-path change.

## Fixture

`local_agent/evaluations/retrieval_hand_judged.json`

- 18 queries (15–20 bar). 17 paraphrases + 1 lexical (`judge_transcript`
  NotRegistered — that failure really was looked up by name).
- Each `relevant_chunk_id` was opened in the index and contains the answer,
  not a topical mention. `TODO.md` / `RAG_EVALUATION.md` are not in
  `SOURCE_GLOBS`; ground truth is only indexed files.
- `top_k=5` matches `search_docs`. `rerank_window=50` matches Stage 3's
  fused-head window. A hit at rank 6–50 is a FlashRank candidate; a miss
  outside the scorer pool is a Stage 4 rewrite problem.

Runner: `python local_agent/eval_retrieval.py --scorer hybrid --write-results`
(from repo root). `--scorer lexical` for the BM25 baseline. If
`router.CPU_HOST` (:11435) is not listening, hybrid auto-fail-closes
(lexical fallback) instead of hanging on farm 45s + `embed()` 120s/batch.

Tests: `python -m unittest local_agent.test_retrieval_eval -v` — **6/6
passed** in 5.7s (fixture integrity, disk chunk-id check, lexical smoke,
hybrid fail-closed ranks match lexical). No Ollama. No GPU.

## HybridScorer result (this run)

CPU Ollama `:11435` was down; GPU `:11434` was not used (EmbeddingScorer
never touches the 5080). Hybrid therefore fail-closed, same ranking as
LexicalScorer. Live dense Hybrid remains unmeasured until nomic-embed-text
is reachable on CPU_HOST.

Live index at run time: **992 chunks** (judgment used the 940-chunk
2026-09-03T07:17:36Z snapshot; all 18 ground-truth ids still resolved).

**13/18 in top-5. 5/18 outside top-5. 0 missing from the scorer pool.**
All five misses sit in the Stage 3 window (ranks 7–19):

| id | query (short) | best rank |
|---|---|---|
| compaction_prefetch_threshold | context fill fraction for prefetch | 7 |
| gpu_idle_but_cpu_8b | GPU chat on CPU 8B with empty VRAM | 10 |
| wireguard_icmp_not_health | ping to hub fails, is farm down? | 15 |
| relullama_not_promotable | ReluLLaMA in the model picker? | 17 |
| empty_search_means_unsupported | empty search_docs → answer from training? | 19 |

The other 13, including several paraphrases (`changelog letter`, `source
citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs
seed), ranked 1–3.

Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`.

## What this does to the FlashRank decision

2026-09-03ae parked Stage 3 because quality vs **this** HybridScorer was
unmeasured. It is now measured on fail-closed Hybrid:

- **FlashRank can in principle help** — 5/18 queries already retrieve the
  right chunk into the fused head but not into `search_docs`' top-5. That
  is exactly what a cross-encoder on top-50 is for. None of the 18 need
  Stage 4 to recover a chunk that was never retrieved.
- **Not yet a default-path install.** Dense Hybrid (nomic-embed-text on
  :11435) was not run; it might already promote some of those five.
  TinyBERT vs MiniLM-L-12, RSS, and 61% chunk truncation are unchanged.
  Re-run `eval_retrieval.py --scorer hybrid --write-results` once CPU
  embed is up; if `n_flashrank_candidate` stays >0, that is the install
  go. If it drops to 0, FlashRank stays parked.

No `pip install flashrank`. No `RerankedScorer`. `_DEFAULT_SCORER` stays
HybridScorer. `APP_REVISION` unchanged. GUI not started.

## Files

- `local_agent/evaluations/retrieval_hand_judged.json` (new)
- `local_agent/evaluations/retrieval_hand_judged_last_run.json` (new)
- `local_agent/eval_retrieval.py` (new)
- `local_agent/test_retrieval_eval.py` (new)
- `TODO.md` Phase 2 item 4 Stage 3 / Stage 5 notes
- `RAG_EVALUATION.md` Stage 5
- `docs/hybrid_scorer_proposal.md` 2026-09-03aj addendum
