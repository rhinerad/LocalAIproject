# 2026-09-03ad — Unguarded answer-path tool-exception handling

## What changed

**`local_agent/agent.py`** — every remaining `tools.call(...)` inside `answer()` (and helpers it invokes during a turn) now uses the same hop-loop pattern already applied in 2026-09-03a:

```
try:
    result = tools.call(...)
except Exception as exc:
    result = f"ERROR: {type(exc).__name__}: {exc}"
```

The hop-loop itself was already guarded. This pass wraps the sibling paths that could still let a tool-runtime exception escape `answer()`, skip `finish_turn`, and leave busy/`in_progress` stuck.

**`local_agent/test_native_tool_calling.py`** — five regression tests added immediately after the two 2026-09-03a tests:
- `test_execute_plan_tool_exception_is_caught_not_raised`
- `test_execute_plan_second_step_still_runs_after_first_raises`
- `test_url_prefetch_tool_exception_is_caught_not_raised`
- `test_start_current_chat_render_shortcut_exception_is_caught_not_raised`
- `test_sonic_pi_ensure_exception_is_caught_not_raised`

Test count: 60 → 65. New tests pass. `test_action_resolver` still passes (29 tests).

## Path-by-path trace

### Already guarded (left unchanged)

1. **Hop-loop mixed-hop main-thread `run_one()`** — wrapped in 2026-09-03a.
2. **Hop-loop pooled `fut.result()`** — already wrapped before 2026-09-03a.
3. **Hop-loop sequential else-branch `run_one()`** — wrapped in 2026-09-03a.
4. **`run_one()` itself** — returns `tools.call(...)`; callers wrap. No second hop-loop copy.
5. **`tools.call()` dispatch** — still converts `ToolError` / `Exception` from the tool body into an ERROR string. The hop-loop wrap is defense-in-depth for when `tools.call` itself raises (the 2026-09-03a threat model: patched/raising `tools.call`).
6. **`@_chat_busy_guard`** — `try/finally` resets busy and re-raises. It is not an ERROR converter and is not supposed to be; wrapping the tool calls is what lets `finish_turn` run.
7. **`server.py` `_send_turn`** — outer `except Exception` pushes `"error"` to the GUI. It does **not** call `finish_turn`; that still depends on `answer()` returning.
8. **`server.py` `/api/action` and `/api/state`** — GUI/direct tool dispatch, not a chat hop-loop, not `begin_turn`/`in_progress`. `tools.call` already converts tool-body exceptions. `/api/stop_comfyui` already has its own try/except. Left as-is (not the hop-loop class).
9. **`action_resolver.classify()`** — maps requests to `(tool, args)` only; it does not execute tools.
10. **`subtask_dispatch._run_one()`** — worker LLM call, already returns `ERROR: worker failed: ...`. Not a tool hop.
11. **`draft_prompt()` `clip_info`** — not inside `answer()`; a separate drafting API. Left as-is (supposed to surface to that caller).
12. **`lxmf_agent` schedule-cancel `tools.call`** — phone fast-path, not `answer()` hop-loop. Left as-is.
13. **No computer-use / second hop-loop copy** in `agent.py`. Native and legacy (`TOOL:` text) both feed the same guarded `hop_calls` / `run_one` loop.

### Newly wrapped (same ERROR pattern)

14. **`_execute_plan()` sequential `tools.call`** — the closest sibling. Action-resolver plans run this for-loop instead of the hop-loop. Unguarded raise exited `answer()` before `finish_turn`. Now per-step try/except; later steps still run.
15. **`add_supplied_url_evidence()` `fetch_url` / `list_memory`** — pre-hop prefetch inside `answer()`. A raise aborted the turn before the model ran.
16. **`_prefetch_requested_project_evidence()` `search_docs`** — same pre-hop abort.
17. **`start_current_chat_render` shortcut** — deterministic path in `answer()`; a raise skipped `finish_turn`.
18. **`ensure_sonic_pi` / `stop_sonic_pi`** — deterministic path in `answer()` before the hop-loop.

KeyboardInterrupt / SystemExit are not caught (`except Exception`). Programmer errors outside tool execution still raise.

## Evidence

`python -m unittest test_native_tool_calling -v` — 65 tests. The five new tests pass. `test_concurrency_safe_tools_run_in_parallel_within_one_hop` is a pre-existing timing flake (`elapsed` ~0.56–0.70 vs `< 0.55`); this patch did not touch the hop-loop.

`python -m unittest test_action_resolver -v` — 29 tests, 0 failures.

## Scope

`APP_REVISION` is unchanged — no transport-visible behaviour changed. The error that was a 500 / stuck `in_progress` is now an ERROR string inside a normal reply. `START_LOCAL_AGENT_GUI.ps1` does not need updating.
