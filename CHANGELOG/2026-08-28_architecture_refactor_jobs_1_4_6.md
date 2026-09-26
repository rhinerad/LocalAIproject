# 2026-08-28 — Local-agent architecture refactor: jobs 1–4 and 6

## Completed structural work

### Job 1 — one atomic write primitive

- Added `local_agent/atomic_io.py` with `atomic_write_text()` and
  `atomic_write_json()`.
- Migrated the fourteen audited local-agent state writers to that primitive:
  `agentic_state`, `exemplar_curator`, `exemplar_embeddings`,
  `exemplar_lifecycle`, `gpu_gate`, `learning`, `media_queue`,
  `media_watcher`, `memory`, `phone_scheduler`, `remote_security`,
  `retrieval`, `router`, and `store`.
- JSON layout and public helper signatures are unchanged. `rg` confirms that
  the audited tree's only remaining direct write replacement is the shared
  primitive itself; the remaining `media_queue` replacement is a deliberate
  state-file move, not a write implementation.

### Job 2 — one guarded persistent Chroma client

- Added a module-level, lock-protected `PersistentClient` cache to
  `exemplar_embeddings.py` and a private test-only reset hook to close the
  cached handle when an isolated temporary DB is torn down.
- Added `test_exemplar_embeddings_concurrency.py`, which runs a real one-cycle
  background sync alongside foreground `retrieve()` and `semantic_duplicate()`
  against one on-disk Chroma directory.
- The pre-refactor race did not surface an operation exception, but it left a
  Windows file handle open and made temporary-directory cleanup fail with
  `WinError 32`. The singleton plus explicit test teardown removes that failure.

### Job 3 — shared CPU pair hand-off selection

- Extracted the paired CPU fallback store selection into
  `router._paired_cpu_fallback()`.
- It continues to prefer the dedicated CPU store, then reuses a GPU-store copy
  only with `num_gpu=0`; the GPU-busy, eviction, and four-thread safeguards are
  unchanged.

### Job 4 — one CPU context-window policy source

- `ollama_client.DEFAULT_OPTIONS["num_ctx"]` now imports
  `router.CPU_OPTIONS["num_ctx"]` rather than carrying a third independent
  `16384` literal.
- Added `test_ollama_context_options.py` to make future policy drift fail fast.

### Job 6 — documentation correction and drift record

- Corrected `local_agent/UPGRADE/00_INDEX.md` row 12: `propose_file_diff` is
  implemented and registered, not an unbuilt review item.
- `local_agent/UPGRADE/BUILD_STATUS.md` intentionally points to
  `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-26.md`, but that target is dated
  2026-08-26 and reports older test counts. This is recorded as status-chain
  drift only; this refactor does not attempt to merge or rewrite the status
  documents.

## Verification

- Atomic-writer module regressions passed before and after migration:
  `test_agentic_state` (9), `test_exemplar_curator` (3),
  `test_exemplar_embeddings` (2), `test_exemplar_lifecycle` (1),
  `test_gpu_gate` (6), `test_media_gpu_queue` (26),
  `test_media_watcher_exact_qwen` (5), `test_memory_extractor` (3),
  `test_phone_scheduler` (12), `test_lxmf_bridge` (11),
  `test_retrieval_relevance` (2), and `test_router_switching` (27).
- Job 2: `test_exemplar_embeddings` (2), new concurrency test (1), and
  `test_optional_deps` (22; 2 expected dependency-present skips) pass.
- Jobs 3–4: `test_router_switching` remains 27/27 before and after; new context
  option equality test passes; `test_native_tool_calling` remains 28/28.
- `validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.
- Tool-schema catalog observed at **52**, not the audit prompt's stale 48. No
  tool was added or removed in this refactor.

## Explicitly not started

Job 5 (the five-stage `agent.answer()` context-prefetch extraction) was not
started. It is larger than the completed structural changes and must be done as
one clean migration with `test_native_tool_calling` and
`test_context_resilience` held constant; `agent.py` remains unchanged by this
entry.
