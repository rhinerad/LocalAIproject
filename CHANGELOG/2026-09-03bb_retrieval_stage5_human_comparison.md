# 2026-09-03bb — RAG Stage 5: live-dense human comparison (mixed, keep Hybrid)

Letter from `python scripts/next_changelog_id.py` immediately before write.

`search_docs` already defaulted to `HybridScorer` (2026-09-02ab). In
practice it was still lexical whenever CPU Ollama `:11435` was down
(fail-closed). This session ran the missing human comparison: the 18-query
fixture `local_agent/evaluations/retrieval_hand_judged.json`, lexical
`search_docs` vs live-dense Hybrid, with nomic-embed-text actually up.

**Decision: mixed, not a clear win. Do not change `_DEFAULT_SCORER`.
Keep Hybrid. Do not revert to lexical.** Fail-closed Hybrid is still
identical to BM25. Live dense is a net +1 gold in search_docs top-5
(13/18 vs 12/18) and recovers three paraphrases lexical ranked 6–16, but
it also buries two questions lexical already answers in top-2.

No FlashRank. No `APP_REVISION` bump. GUI not started. GPU Ollama
`:11434` was not used for embeddings.

## What was compared

- **Lexical:** `LexicalScorer` + the same `search_relevant` filter
  `search_docs` uses. This is what the tool returns today when the dense
  side fail-closes.
- **Hybrid:** real `HybridScorer` RRF over the live index, chunk+query
  vectors from `nomic-embed-text:latest` on a CPU-only Ollama at
  `:11435` (`CUDA_VISIBLE_DEVICES=-1`, `OLLAMA_VULKAN=false`, log line
  `inference compute id=cpu`, `total_vram=0 B`). First start with only
  `CUDA_VISIBLE_DEVICES=-1` still discovered the RTX 5080 over Vulkan;
  that process was killed before any embed. Cache warmed to 100%
  (1040/1040 then 1041 chunks).

Runner: `python -u local_agent/eval_retrieval_human.py`.
Side-by-side packet:
`local_agent/evaluations/retrieval_human_side_by_side.md` (and `.json`).
Official scorer run (same live-dense Hybrid):
`python local_agent/eval_retrieval.py --scorer hybrid --write-results`
→ `retrieval_hand_judged_last_run.json` and snapshot
`retrieval_hand_judged_live_dense.json`.

## Mechanical (supporting)

| | lexical search_docs | live-dense Hybrid search_docs |
|---|---|---|
| gold chunk in the 5 results the tool would return | 12/18 | 13/18 |
| gold rank ≤5 (raw scorer) | 12/18 | 13/18 |
| FlashRank-window only (ranks 6–50) | — | 5/18 |
| missing from pool | — | 0 |

Hybrid recoveries (lexical missed the gold in the tool's top-5):

| id | query (short) | lex rank | hy rank |
|---|---|---|---|
| gpu_idle_but_cpu_8b | GPU chat on CPU 8B, empty VRAM | 10 | 2 |
| farm_embed_no_celery_import | embed jobs without importing Celery | 6 | 2 |
| relullama_not_promotable | ReluLLaMA in the picker? | 16 | 3 |

Lexical still wins (gold in lexical search_docs, hybrid drops it out of top-5):

| id | query (short) | lex rank | hy rank | why lexical is more useful |
|---|---|---|---|---|
| phase1_stay_on_ollama | stay on Ollama or switch to PowerInfer? | 1 | 9 | Lexical #1 is the Phase 1 close note. Hybrid's top-5 is older PowerInfer scaffold/pipeline/picker docs — the opposite of the answer. |
| judge_not_registered | first judge_transcript NotRegistered | 2 | 12 | Lexical #2 is the "Step 2 — root cause of NotRegistered" chunk (the exact name lookup). Hybrid keeps the same file's intro but not that section. |

Both miss (gold outside search_docs top-5 either way):
`empty_search_means_unsupported` (lex 25 / hy 43),
`compaction_prefetch_threshold` (lex 10 / hy 8),
`wireguard_icmp_not_health` (lex 15 / hy 10). Hybrid moved two of those
closer; none entered top-5. Stage 3 FlashRank still has a 5-query window.

On the other 10, both return the gold. Hybrid often ranks it 1st instead
of 2nd/3rd (`duration_ladder_not_seed`, `tinyengine_is_mcu`,
`agentic_retry_loop`, `farm_status_snapshot`, `flashrank_catalog_names`).
That is a real but small usefulness lift — not enough to call the set a
clear win, given the two regressions.

## Default

`_DEFAULT_SCORER` stays `HybridScorer()`. Tests already assume that
(`DefaultHybridScorerTests`); none still assert lexical-only as the
`search_docs` default. No test change.

Fail-closed path is unchanged: `test_hybrid_fail_closed_matches_lexical_best_ranks`  still passes.

## Tests this session

```
python -m unittest local_agent.test_retrieval_eval local_agent.test_retrieval_embeddings local_agent.test_retrieval_relevance -v
```

**23/23 passed** in 5.1s. No Ollama in those tests.

## Files

- `local_agent/eval_retrieval_human.py` (new runner)
- `local_agent/evaluations/retrieval_human_side_by_side.json`
- `local_agent/evaluations/retrieval_human_side_by_side.md`
- `local_agent/evaluations/retrieval_hand_judged_last_run.json` (live-dense)
- `local_agent/evaluations/retrieval_hand_judged_live_dense.json` (snapshot)
- `TODO.md` Phase 2 item 4 Stage 5 note
- `RAG_EVALUATION.md` Stage 5
- `docs/hybrid_scorer_proposal.md` addendum
