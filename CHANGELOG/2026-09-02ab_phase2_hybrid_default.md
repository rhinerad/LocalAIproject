# 2026-09-02ab — Phase 2 RAG: FlashRank deferred; HybridScorer default

## FlashRank / Stage 3 — explicit deferral (nothing installed)

Decision this session: **do not add FlashRank, onnxruntime, or
`ms-marco-MiniLM-L-6-v2`.** That is a new runtime dependency, same bar as
PowerInfer / TinyChatEngine. Stage 4 already gives a HybridScorer-backed
path via `agentic_search_docs`. Stage 3 can wait for a later explicit
new-dependency approval. Best-fit candidate from 2026-09-02m is unchanged
if revisited.

## Stage 5 cheap comparison (this session, not a large eval)

CPU Ollama on `:11435` was down; GPU `:11434` was not used. No models
downloaded. Comparison:

1. **Mocked fixture** (two chunks: farm-liveness paragraph vs prompt-prefix
   distractor; embeddings mocked, no network):
   - lexical query `Celery inspect ping liveness`: Lexical 1/1, Hybrid 1/1
     (relevant chunk recalled by both)
   - semantic paraphrase `tell whether queued task daemons died`: Lexical
     0/1, Hybrid 1/1 (Hybrid recovered the miss; Lexical had no term overlap)
   - **recall 2/2 Hybrid vs 1/2 Lexical** — Hybrid not worse
2. **On-disk, embeddings failing closed** (real `retrieval_index.json`, 856
   chunks; `ollama_client.embed` raises `ConnectionError` so Hybrid falls
   back to lexical-only). Top-5 chunk ids matched Lexical exactly on:
   - `source citation contract`
   - `changelog letter convention`
   - `farm status snapshot daemon`
   Lexical-only top hits (baseline, recorded before the default flip):
   - `source citation contract` → `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md`,
     `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`,
     `CHANGELOG/2026-09-02b_source_citation_contract.md`
   - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md`
   - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md`

A larger hand-judged query set remains an operator lever, not a block.

## What was wired

Smallest default-behavior change that does not break tool contracts:

- `retrieval._DEFAULT_SCORER` is now `HybridScorer()`. `search()` /
  `search_docs` use hybrid unless a caller passes `LexicalScorer()`.
- `HybridScorer` tags each hit `_match_by` = `lexical` / `embedding` /
  `both` (shallow copy; index chunks are not mutated). `search()` surfaces
  `match_by` on results.
- `search_relevant()` keeps embedding-only hits (`match_by` in
  `embedding|both`) even with no term overlap, and still drops untagged
  lexical near-misses. Existing relevance tests that mock `search()` without
  `match_by` keep the old filter.
- `agentic_search_docs` stays a **separate** tool: still in
  `PROJECT_ONLY_TOOLS`, still **not** in `CONCURRENCY_SAFE_TOOLS` (it calls
  the model). `search_docs` remains concurrency-safe. Tool text now calls
  `agentic_search_docs` preferred for judged/cited answers; `search_docs`
  is the fast hybrid chunk-list lookup.
- First live `search_docs` after this change may embed uncached chunks via
  the existing farm-then-local path, then cache them. If embeddings fail,
  ranking falls back to lexical.

Not done: `search_docs` does not call `agentic_search_docs` (that would
remove it from `CONCURRENCY_SAFE_TOOLS` and change the return shape).
FlashRank not installed. GUI not started. `APP_REVISION` not bumped
(another worker owns native-tool-calling).

## Tests

From repo root, Windows Python 3.12.10 (not `worker_farm/.venv`):

```
python -m unittest local_agent.test_retrieval_embeddings local_agent.test_agentic_retrieval local_agent.test_retrieval_relevance -v
```

**25/25 passed** in 1.375s (11 embeddings including default-hybrid +
session comparison, 8 agentic, 6 relevance including semantic-keep).
Did not run `test_native_tool_calling.py` (parallel worker;
`CHANGELOG/2026-09-02aa_native_tool_calling.md`).

## Files

- `local_agent/retrieval.py`
- `local_agent/tools.py`
- `local_agent/agentic_retrieval.py`
- `local_agent/test_retrieval_embeddings.py`
- `local_agent/test_retrieval_relevance.py`
- `local_agent/test_agentic_retrieval.py`
- `TODO.md` (Phase 2 item 4 Stage 3 deferred, Stage 5 wired)
- `RAG_EVALUATION.md` (Stage 5 / FlashRank deferral notes)
- `GROK_STATUS.md` (Current)
