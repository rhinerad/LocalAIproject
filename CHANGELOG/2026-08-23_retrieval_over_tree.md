# 2026-08-23 — UPGRADE 02 (retrieval half): BM25 search over the document tree

## What changed

### local_agent/retrieval.py (new)
- stdlib-only BM25 retrieval. No rank_bm25, no sklearn, no downloads.
- `LexicalScorer` — 35-line BM25 (K1=1.5, b=0.75). Swappable via `ScorerProtocol`.
- `EmbeddingScorer` — stub placeholder for UPGRADE 05's embedding model.
- Indexes 77 files across `docs/**/*.md`, `CLAUDE.md`, `README.md`,
  `CHANGELOG/*.md`, `START_*.md`, `local_agent/UPGRADE/*.md`, and
  `outputs/equal_shares/runtime/agent_questions.md`.
- Chunks at ~3000 chars (~800 tokens) with ~375-char (~100-token) overlap,
  breaking at heading boundaries where possible.
- Excludes `archive/`, `_QUARANTINE_*`, `*.BACKUP*`, and files whose first five
  lines open with a SUPERSEDED banner.
- Persists the index at `knowledge/retrieval_index.json` keyed by mtime+size;
  rebuilds only changed files. Startup time: index loads from disk in < 1 s.
- Public API: `search(query, max_results, scorer)`, `rebuild()`, `load_index(force_rebuild)`.

### local_agent/tools.py
- Added `search_docs(args)` — calls `retrieval.search()`, returns top chunks with
  source file and heading. `{"query": "...", "max_results": 5}`. Read-only.
- Added `search_docs` to TOOLS dict and to `_SCHEMAS`.

### local_agent/agent.py
- Added `# Project documentation` section to `CONVERSATION_RULES`: for any
  question about a rule, a decision, why something works the way it does, or
  project history — call `search_docs` first; `read_doc` stays for reading a
  whole named file.
- Added `_trim_context(msgs, num_ctx, tool_schemas, emit)` — drops oldest
  interior turns until estimated token count fits the model's `num_ctx` window.
  Always preserves: `msgs[0]` (system prompt), `msgs[1]` (original user turn),
  `msgs[-2:]` (immediate prior context for the current hop). Emits a `note`
  event when trimming occurs.
- Added trim guard in the `answer()` hop loop: after routing and emitting the
  `route` event, compares `estimate_context_tokens(msgs, tool_schemas)` against
  `route.options()["num_ctx"]`; calls `_trim_context` if the estimate exceeds it.

### local_agent/build_knowledge_pack.py
- `build_system_prompt()` rewritten to a ~4 KB brief (was ~8.1 KB).
  Removed: "How to behave" section (covered by `CONVERSATION_RULES`), full
  worked prompt example (retrievable via `search_docs`), "A correction you must
  not undo" section, and "What runs next" command list. Kept: verification rule,
  render settings table, prompt format rules (no example), two voice rules,
  current-state block, and standing constraints.
- Warning threshold changed from 16 KB to 8 KB.
- `main()` now calls `retrieval.rebuild()` and reports file/chunk/size stats.

### local_agent/README.md
- Added `retrieval.py` and `knowledge/retrieval_index.json` to the files table.
- Updated `knowledge/SYSTEM_PROMPT.md` description from "9.5 KB" to "~4 KB".

## Why

The agent could only answer from a 9.5 KB compiled digest of a ~200 KB doc tree.
Ask about a specific CHANGELOG measurement or a paragraph of `H3_PROMPT_RULES.md`
and it either read the whole file or guessed. The retrieval tool lets it fetch
the relevant chunk and cite exactly where the claim came from — which is the
project's standard of evidence. The smaller brief frees context budget for the
adaptive reasoning pair's wider windows (14B: 20 K tokens, 8B: 32 K tokens).

The context-trim guard prevents silent token overflow: without it, a long
conversation that exceeds `num_ctx` would produce garbage answers with no warning.

## Evidence

### Index build
```
python local_agent/build_knowledge_pack.py
system prompt : 3.9 KB  (597 words)
retrieval index: 77 files  306 chunks  1541.9 KB
```

### Brief before vs after
Before (measured from SYSTEM_PROMPT.md before this change): ~8.1 KB
After: **3.9 KB** ✓ (target < 6 KB)

### Search verification
```
python local_agent/retrieval.py "why was the pace corrected to 2.5"
[11.457] CHANGELOG/2026-08-17b_pace_correction_and_auditions.md  ← rank 1 ✓

python local_agent/retrieval.py "duration ladder"
[6.636] CHANGELOG/2026-08-19_local_agent_first_live_run.md
[6.284] CHANGELOG/2026-08-18_duration_ladder.md  ← in top 2 ✓
```

### Exclusion verified
```python
# archive/ directory: NONE in index ✓
# archive/superseded_docs/TECHNICAL_OPERATIONS.md in index: False ✓
# BACKUP and SUPERSEDED named files: NONE ✓
```

### Incremental rebuild verified
```python
# Touch CLAUDE.md → only CLAUDE.md re-indexed: True ✓
```

### Regression
```
python -m unittest test_native_tool_calling   # 9/9 OK ✓
python validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v
# 124/124 valid ✓
search_docs in schemas: True ✓
```

## What is still unverified

- End-to-end: a live model conversation using `search_docs` and citing the
  returned source file has not been observed. The tool is wired and the index is
  built; this waits for a real model interaction.
- Startup timing under 1 second not measured on a cold disk cache — only tested
  on a warm OS cache. The index is 1.5 MB; reading it from an SSD should be well
  under 1 s.
- `_trim_context` has not been triggered in a real conversation (would require
  a context exceeding 20 K–32 K tokens for the primary/fallback models).
- `EmbeddingScorer` is a stub; it raises `NotImplementedError` until UPGRADE 05.

## What the num_ctx half of UPGRADE 02 was and why it was not re-done

The original UPGRADE 02 had two halves:
1. **num_ctx** — raise context from 8 K to 32 K. Already delivered by the
   adaptive reasoning pair in `router.py`: primary 14B gets 20 480, fallback 8B
   gets 32 768. Changing those values here would fight the existing logic.
2. **Retrieval** — BM25 search over the doc tree. This is the half built here.

Only the retrieval half was outstanding.
