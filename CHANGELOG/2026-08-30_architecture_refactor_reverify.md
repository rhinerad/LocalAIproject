# 2026-08-30 — UPGRADE 24 architecture refactor re-verified

Fresh pass against `00_INDEX.md` row 24 and
`CHANGELOG/2026-08-28_architecture_refactor_jobs_1_4_6.md` /
`CHANGELOG/2026-08-28_context_prefetch_extraction.md`. No production files
were edited. `router.py`, `tools/powerinfer/`, and `work/` were not touched.

## Tests (real counts, this session)

From `local_agent/`:

| Suite | Result |
|---|---|
| `test_ollama_context_options.py` | 1/1 OK |
| `test_context_prefetch.py` | 2/2 OK |
| `test_exemplar_embeddings.py` | 2/2 OK (18.699s) |
| `test_exemplar_embeddings_concurrency.py` | 1/1 OK (2.299s) |
| `test_gpu_gate.py` | 6/6 passed |
| `test_agentic_state.py` | 11/11 OK (changelog had 9; suite grew) |
| `test_memory_extractor.py` | 3/3 OK |
| `test_context_resilience.py` | 5/5 PASS |
| `test_optional_deps.py` | 22/22 OK, 2 skipped (chromadb/cryptography present) |
| `test_phone_scheduler.py` | 14/14 OK (changelog had 12; suite grew) |
| `test_exemplar_curator.py` | 3/3 OK |
| `test_exemplar_lifecycle.py` | 1/1 OK |

`test_router_switching.py` was **not** re-run: another session owns `router.py`
today. Job 3 was checked by reading the code (`_paired_cpu_fallback` exists
and is called from `decide()`).

## Job 1 — 14 writers vs `atomic_io`

`atomic_io.atomic_write_text` is the tmp-then-`os.replace` helper. Direct
reads of the audited files:

| File | Uses `atomic_write_text` |
|---|---|
| `gpu_gate.py` | yes (`_save` → `atomic_write_text(STATE_FILE, ...)`) |
| `store.py` | yes (conversation JSON) |
| `memory.py` | yes (`_STORE`) |
| `agentic_state.py` | yes (checkpoint JSON) |
| `media_queue.py` | yes (job JSON; `os.replace` remains only for moving a job file between queue dirs) |
| `retrieval.py` | yes (index JSON) |
| `exemplar_curator.py` | yes |
| `exemplar_embeddings.py` | yes (sidecar JSON) |
| `exemplar_lifecycle.py` | yes |
| `media_watcher.py` | yes (owner file) |
| `remote_security.py` | yes |
| `phone_scheduler.py` | yes (job JSON); also `open(..., "a")` for an append-only log, not the tmp-replace pattern |
| `learning.py` | yes (`REVIEW`); JSONL ledger still appends with `open(..., "a")` |
| `router.py` | yes (`CHAT_BUSY_FILE`) — read only, not edited |

The four requested spot-checks (gpu_gate, store, memory, agentic_state) all
call the shared helper, not a private `open()`/`write_text()` replace.

## Job 2 — Chroma concurrency test is not identity-only

`test_exemplar_embeddings_concurrency.py` starts `embeddings.start_worker()`
(background thread, `_STOP` forced to one cycle) and a second
`threading.Thread` that loops `retrieve()` + `semantic_duplicate()` twelve
times against the same temp `DB_DIR`. It asserts both threads finish, no
exceptions, and the approved record is `"embedded"`. That is concurrent
access to one on-disk store, not `assert client is client`.

`exemplar_embeddings._client()` is a lock-guarded `PersistentClient`
singleton (`_CLIENT` / `_CLIENT_LOCK` / `_CLIENT_PATH`).

## Jobs 3–6 (code, not re-run of router tests)

- `_paired_cpu_fallback()` is in `router.py` and used from `decide()`. Coding
  still has a follow-on CPU selection block after that shared store choice.
- `ollama_client.DEFAULT_OPTIONS["num_ctx"]` is `router.CPU_OPTIONS["num_ctx"]`
  (1/1 equality test green).
- `agent.answer()` builds `context_prefetch.ContextPrefetcher` with the five
  named stages; 2/2 prefetch tests green.
- `00_INDEX.md` row 12 lists `propose_file_diff` as implemented.

## Verdict

The structural claims hold on this re-run. This is a verification pass, not a
redesign. Full `test_router_switching.py` remains the one row-24 suite not
re-executed here because `router.py` is live in another session.

## Still unverified

- `test_router_switching.py` this session
- `validate_h3_prompt.py` 124/124 this session (standing gate, not row-24-specific)
- `test_native_tool_calling.py` this session
