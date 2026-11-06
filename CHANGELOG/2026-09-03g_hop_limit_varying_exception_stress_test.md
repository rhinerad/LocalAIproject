# 2026-09-03g — Hop-loop MAX_TOOL_HOPS stress test (varying args_sig)

## What changed

**`local_agent/test_native_tool_calling.py` only.** `agent.py` not touched.

Added `test_varying_exception_args_sig_hits_max_tool_hops_instead_of_hanging`
immediately after `test_failing_tool_call_with_varying_arguments_is_not_treated_as_stuck`.

The test mocks a model that keeps calling `web_search` with a new query every
hop (`q1`, `q2`, …) while `tools.call` raises a unique `RuntimeError` each time
(`injected failure #N`). That combination:

- converts to an ERROR string via the 2026-09-03a main-thread exception wrap
- changes `args_sig` every hop, so the repeated-failure guard
  (`same name + same args`, `REPEATED_FAILURE_LIMIT = 3`) cannot fire
- must terminate on the `MAX_TOOL_HOPS = 6` backstop instead of hanging

Assertions: `answer()` returns in under 5s, reply is not the stuck-guard
`Stopped:` text, model turns == `MAX_TOOL_HOPS + 1`, tool raises ==
`MAX_TOOL_HOPS` (the last hop does not execute tools), and an `on_event`
note contains `hop limit`.

Native-tool count: 59 → 60.

`APP_REVISION` unchanged.

## Evidence (DuranGamingPC, Python 3.12.10, not farm venv)

Repo root, `$env:PYTHONIOENCODING='utf-8'`, interpreter
`A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe`.

- New test alone: **ok in 2.171s**.
- `python -m unittest local_agent.test_native_tool_calling -v`: **60 ran, 1 failed**
  in 26.445s. The new test passed. The failure is
  `test_concurrency_safe_tools_run_in_parallel_within_one_hop`
  (`elapsed` 0.91–0.94s vs `< 0.55`); it fails the same way in isolation and
  is a hop-overhead timing bound, not this change. Re-run isolation: 0.939s.
- Full top-level local-agent sweep (79 modules, `local_agent/test_*.py`, not
  worker_farm): **604 ran in 189.044s, FAILED (failures=3, skipped=2)**.
  Failures:
  1. `test_concurrency_safe_tools_run_in_parallel_within_one_hop` (timing bound)
  2. `test_existing_whisper_capability_routes_transcription_without_loading_a_model`
     (`caps["available"]` is False on this machine)
  3. `test_non_render_turn_gets_scope_boundary_not_old_render_checkpoint`
     (expected `Scope boundary for this turn` missing from injected system text)
- Worker-farm isolated venv, all `local_agent.worker_farm.test_*`:
  **71 ran in 6.249s, OK (skipped=10)**. Live farm workers were down
  (`no_workers`), so integration tests skipped as designed.

## Scope

Test-file + this changelog + GROK_STATUS. No `agent.py` change.
