# 2026-08-22 — the native-function-calling regression suite, recorded

No source code changed in this entry. It records an existing test artifact that
the handoff never pointed at, and adds the pointers so the next agent can find it.

## 1. What changed

- `CHANGELOG/2026-08-22_regression_suite_recorded.md` — this entry.
- `CHANGELOG/README.md` — new row in the Files table for this entry.
- `local_agent/README.md` — a **Regression tests** line naming
  `test_native_tool_calling.py` and the command to run it.

`local_agent/test_native_tool_calling.py` itself was already in the tree. Its
source content matches the native-function-calling work recorded in
`2026-08-19_native_function_calling.md`; only the handoff pointers were missing.

## 2. Why

The `2026-08-19` entry describes verification checks (schema/enum counts, guard
rails, multi-call-in-one-hop, legacy fallback) but its **Files changed** table
lists only `tools.py`, `ollama_client.py`, and `agent.py`. The committed test
that automates those checks — `local_agent/test_native_tool_calling.py` — was
referenced by **no** document in the tree:

    $ grep -rn "test_native_tool_calling" --include=*.md .
    (no matches)

A regression suite nobody knows to run is a suite that silently rots. This entry
makes it findable.

## 3. The evidence

Ran on this machine's CPython, 2026-08-22:

    $ python local_agent/test_native_tool_calling.py
    test_all_schemas_and_enums ... ok
    test_chat_passes_tools ... ok
    test_guard_rails ... ok
    test_legacy_fallback_logs_and_runs ... ok
    test_multiple_calls_one_hop_and_named_results ... ok
    test_persistence_attachment_shape_and_regenerate_primitive ... ok
    test_stop_path ... ok
    ----------------------------------------------------------------------
    Ran 7 tests in 0.125s
    OK

What the 7 tests actually assert:

1. `schemas()` returns 14 tool schemas; every `required` field is a subset of
   `properties`; the `run_build` / `propose_gpu` / `read_doc` enums match the
   live `tools.BUILD` / `tools.GPU` / allowed-doc dicts.
2. `chat()` forwards the `tools=` schemas to Ollama and returns the parsed
   `tool_calls`.
3. Two tool calls in a single model hop both run, and each result comes back as a
   `role:"tool"` message tagged with its function name.
4. The legacy `TOOL:` text protocol still fires as a fallback and emits a `note`.
5. Guard rails refuse: unknown tool, path-traversal clip id, `/etc/passwd` doc,
   `rm -rf /` build action, and a write to a protected project file.
6. Conversation persistence: append, truncate-after (regenerate primitive),
   rename, and delete-to-`_deleted`.
7. The stop path returns the partial reply marked `_[stopped]_`.

## 4. What was verified after

- `grep -rn "test_native_tool_calling" --include=*.md .` now returns matches in
  this entry, `CHANGELOG/README.md`, and `local_agent/README.md`.
- The test command above re-run: still 7/7 OK.

## 5. Still unverified

- **This was a stdlib-only run.** No live Ollama was contacted. Everything in
  `MORNING_CHECK.md` that needs a real model — GPU-idle → GPU-tier routing, and
  whether `qwen2.5-coder:14b` honours the native protocol — remains untested.
- No claim is made that source changed since 2026-08-20. On this SMB-mounted
  tree file mtimes update on access and are not a reliable "what changed" signal;
  this entry relied on file **content**, not timestamps.
- Every `local_agent/UPGRADE/` prompt except 01 is still unexecuted, unchanged
  from the 2026-08-20 entry.
