# 2026-08-31 — parallel tool execution, a bounded sub-agent primitive, and CPU thread-cap consolidation

## What changed

Three follow-ups from an architecture-vs-standard-agent-harness comparison
(and its own follow-up safety-invariant audit). One additional item from
that same audit (protected-file scoping) was reviewed and deliberately left
unchanged — see the end of this entry.

**1. Parallel tool execution within one hop, in `agent.py`.**

The model has always been able to return several tool calls in a single
hop (`test_multiple_calls_one_hop_and_named_results` predates this change),
but `agent.py`'s execution loop ran them strictly sequentially — a plain
`for tc in hop_calls:` loop blocking on each `tools.call()` before starting
the next.

Added `tools.CONCURRENCY_SAFE_TOOLS`, a explicit allow-list of tools that
are pure reads with no shared mutable state and no GPU-model load: project
docs/state lookups, file reads, `list_dir`/`inspect_workspace`/
`inspect_binary`, `fetch_url`/`web_search`, `list_memory`/
`list_phone_schedules`, `read_artifact`, `capabilities`, `audio_measure`,
and `read_video_metadata` (the last two confirmed, by reading
`media_tools.py`, to be ffmpeg/ffprobe-based and CPU-only — not the sibling
functions that load Whisper or a speaker model). Everything else — writes,
batch/render start-stop, Sonic Pi, phone scheduling, `remember_fact`, and
every tool that loads a vision/whisper/speaker model onto the GPU
(`see_image`, `video_frames`, `analyze_video`, `extract_video_actions`,
`transcribe`, `compare_voice`) — is deliberately excluded and stays
sequential on the main thread, so two calls can never race on a lock, a
queue file, or GPU residency.

In `agent.py`'s hop loop: all calls in a hop are now announced (`"tool"`
progress cards) up front, calls in the safe set are submitted to a
`ThreadPoolExecutor` and run concurrently, everything else runs inline on
the main thread, and results are then reported to the model **in the
original call order**, regardless of which one actually finished first. A
hop with only one call (the overwhelming common case) takes the exact same
sequential path as before this existed — nothing changed for it.

**2. A bounded coordinator/worker sub-agent primitive: `dispatch_subtasks`.**

New module `subtask_dispatch.py`, wired into `tools.py` as
`dispatch_subtasks`. Lets the model fan out up to 5 genuinely independent
sub-questions to concurrent CPU workers instead of answering them one at a
time through the main hop loop — the one deliberately narrow "multi-agent"
primitive in this codebase, not a general recursive sub-agent framework:

- Workers are plain text-in/text-out CPU calls with **no tool access at
  all**, so a worker cannot itself recurse into rendering, file writes,
  scheduling, or another `dispatch_subtasks` call.
- Workers are hardcoded to the CPU host with `num_gpu: 0` and
  `router.CPU_THREAD_CAP` threads — never routed through `router.decide()`.
  Several background workers concurrently trying to load a model onto the
  GPU is exactly the kind of race this project's "one backend, ever" rule
  exists to prevent, so this is enforced by construction rather than by
  trusting a per-worker gate to serialize correctly under concurrency.
- Bounded: at most 5 sub-tasks, 500 characters each, 60s timeout per
  worker, refuses to run at all if the worker model (the same
  `context_compactor.MODEL` CPU helper already used elsewhere) isn't
  installed, and a single worker's exception becomes a labeled `ERROR:`
  answer rather than failing the whole batch.
- Results are returned in original task order regardless of completion
  order, same as the parallel-tool-execution change above.

**3. CPU thread cap consolidated to one constant.**

`num_thread: 4` was previously a literal repeated independently in five
places (`ollama_client.py`, `router.py`'s `CPU_OPTIONS`,
`context_compactor.py`, `loop_independent_verifier.py`,
`memory_extractor.py`) — correct everywhere it appeared, but with no single
enforcement chokepoint, so a new CPU call site added later could forget to
set it. Added `router.CPU_THREAD_CAP = 4` as the one source of truth;
all five sites now reference it (all five modules already imported
`router`, so no new import cycle).

## Why

Requested directly, following two prior conversations: a comparison of this
codebase against a generic "how to build agents" writeup (which found no
parallel tool calling and no multi-agent orchestration — both real gaps,
not design choices), and a follow-up safety-invariant audit (which found
the thread-cap duplication and the protected-file basename question).

## What was deliberately NOT changed

**Protected-file basename matching in `tools.py` (`_PROTECTED_NAMES`).**
The audit flagged that it blocks any file with a protected basename
anywhere on disk, not specifically the copy under `outputs/equal_shares/`.
On review this is the *more* conservative behavior: narrowing it to a path
prefix would make a same-named file elsewhere writable again, a strictly
weaker guarantee. Left unchanged; documented as a reviewed-and-kept item in
`TODO.md` rather than silently dropped.

## What was verified

- `python3 -m py_compile` clean on `agent.py`, `tools.py`,
  `subtask_dispatch.py`, `router.py`, `ollama_client.py`,
  `context_compactor.py`, `loop_independent_verifier.py`,
  `memory_extractor.py`.
- `tools.schemas()` still returns exactly one schema per tool
  (`len(tools.TOOLS) == len(tools.schemas())`), confirming
  `dispatch_subtasks` is fully wired into both the dispatch table and the
  native tool-calling schema.
- 8-check standalone script for parallel tool execution: two safe tools
  (`web_search`, `fetch_url`) genuinely overlap in wall-clock time (total
  elapsed ~0.3s for two 0.3s calls, not ~0.6s); a mixed safe+unsafe hop
  keeps the unsafe `write_file` call running start-to-finish without
  interleaving (proof it never entered the thread pool); tool results
  reach the model in original call order even when the second call
  finishes before the first; and a single-call hop is provably unaffected.
- 10-check standalone script for `dispatch_subtasks`: refuses when the
  worker model isn't installed, refuses over 5 tasks, refuses an empty or
  blank task, truncates an oversized task to 500 chars, genuinely runs
  workers concurrently (~0.2s for three 0.2s calls, not ~0.6s), preserves
  task/answer order, survives one worker raising an exception without
  losing the others, and surfaces its `DispatchError` as an `ERROR:` string
  through `tools.call()`.
- Added the same cases as permanent tests: 3 new tests in
  `test_native_tool_calling.py`
  (`test_concurrency_safe_tools_run_in_parallel_within_one_hop`,
  `test_unsafe_tool_stays_sequential_even_alongside_a_safe_one`,
  `test_parallel_tool_results_keep_original_call_order_in_the_transcript`)
  and a new `test_subtask_dispatch.py` (8 tests, including
  `test_workers_never_request_gpu`, which asserts every worker call's
  `options["num_gpu"] == 0` and `num_thread == router.CPU_THREAD_CAP`).
- Full regression sweep (with the documented `set_chat_busy` sandbox
  workaround for the suites that call `agent.answer()`):
  `test_native_tool_calling` 38/38, `test_router_switching` 41/41,
  `test_subtask_dispatch` 8/8 (no workaround needed — doesn't call
  `agent.answer()`), `test_deep_research` 6/6, `test_run_code` 14/14,
  `test_agentic_state` 11/11. 118 tests total, 0 failures, 0 errors.

## What is still unverified

Not yet run on the real Windows workstation. Given the pattern from the
prior two `agent.py` changes this week, that run is expected to pass
without the `set_chat_busy` workaround (which exists only because this
review sandbox cannot delete any file), but it has not been done yet for
this specific change.
