# 2026-09-03a — Hop-loop main-thread exception handling

## What changed

**`local_agent/agent.py`** — two `run_one()` calls inside the hop-loop
tool-execution block were unguarded; any exception raised by an unsafe tool
would propagate out of `answer()` entirely. Both are now wrapped in the same
`try/except Exception as exc: results[i] = f"ERROR: {type(exc).__name__}: {exc}"`
pattern that already existed for the pooled path.

**`local_agent/test_native_tool_calling.py`** — two new regression tests
added immediately after `test_unsafe_tool_stays_sequential_even_alongside_a_safe_one`:
- `test_main_thread_tool_exception_in_mixed_hop_is_caught_not_raised`
- `test_main_thread_tool_exception_in_single_tool_hop_is_caught_not_raised`

Test count: 57 → 59, all pass.

## The gap

The hop-loop tool-execution block has three paths:

```
if len(plans) > 1 and any(n in CONCURRENCY_SAFE_TOOLS for n, _ in plans):
    # mixed hop: safe tools → ThreadPoolExecutor, unsafe tools → main thread
    futures = {i: executor.submit(run_one, n, a) for ...}
    for i, (n, a) in enumerate(plans):
        if i not in futures:
            results[i] = run_one(n, a)          # ← PATH 1, was unguarded
    for i, fut in futures.items():
        try:
            results[i] = fut.result()
        except Exception as exc:
            results[i] = f"ERROR: ..."          # pooled path, was guarded
else:
    for i, (n, a) in enumerate(plans):
        results[i] = run_one(n, a)              # ← PATH 2, was unguarded
```

Path 1 (mixed-hop main-thread slot) and Path 2 (sequential else-branch) had
no `try/except`. Any exception from an unsafe tool — a `PermissionError` from
`write_file`, a `RuntimeError` from a tool checking its preconditions, a network
error from an external call — would propagate out.

## What happened when it fired

1. Exception exits `run_one()` → exits the hop-loop iteration → exits `answer()`.
2. `@_chat_busy_guard` wraps `answer()` with `try/finally` — the finally resets
   `set_chat_busy(False)`, but the decorator does **not** catch exceptions; it
   re-raises.
3. Exception reaches the HTTP transport (Flask/Quart handler) as a 500 error.
4. `agentic_state.finish_turn(cid, ...)` is never called → task state stays
   `"in_progress"` forever.
5. All terminal-guard logic — repeated-failure guard (`REPEATED_FAILURE_LIMIT = 3`),
   hop-limit (`MAX_TOOL_HOPS = 6`), scope-retry, action-retry — is bypassed
   completely.

## The fix

```python
# PATH 1 (mixed-hop main-thread slot)
for i, (n, a) in enumerate(plans):
    if i not in futures:
        try:
            results[i] = run_one(n, a)
        except Exception as exc:
            results[i] = f"ERROR: {type(exc).__name__}: {exc}"

# PATH 2 (sequential else-branch)
for i, (n, a) in enumerate(plans):
    try:
        results[i] = run_one(n, a)
    except Exception as exc:
        results[i] = f"ERROR: {type(exc).__name__}: {exc}"
```

The exception is now caught, converted to an ERROR string, and placed in
`results[i]` exactly as the pooled path's `fut.result()` exception already was.
The model sees it as a normal tool result on the next hop and can decide how
to respond (retry, explain, give up).

## Evidence

`python -m unittest test_native_tool_calling -v` — 59 tests, 0 failures.

Key new tests:

**Mixed-hop test** patches `tools.call` so `web_search` returns `"ok:safe"` and
`write_file` raises `RuntimeError("injected failure")`. Asserts `answer()` returns
`"Recovered."` (a second hop runs, confirming the loop was not aborted) and that
the write_file tool-result message passed to the model on that second hop contains
`"ERROR"`, `"RuntimeError"`, and `"injected failure"`.

**Single-tool test** patches `tools.call` so `write_file` always raises. Asserts
`answer()` returns without raising; the write_file error guard (which fires when all
executed tools are write_file errors) intercepts the ERROR result and returns a
canned message containing the exception detail — confirmed by asserting the reply
contains `"No file was created or changed"`, `"RuntimeError"`, and `"injected failure"`.

## Scope

`APP_REVISION` is unchanged — no transport-visible behaviour changed. The error
that was a 500 is now an ERROR string inside a normal 200 reply. `START_LOCAL_AGENT_GUI.ps1`
does not need updating.
