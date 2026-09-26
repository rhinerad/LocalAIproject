# 2026-09-23h — `_execute_plan` stop-on-ERROR scoped to prompt-pack plans

## Symptom

`python -m unittest test_native_tool_calling` (in `local_agent/`) had one
pre-existing failure:
`NativeToolTests.test_execute_plan_second_step_still_runs_after_first_raises`
— expected `['repair_jsonl_format', 'validate_powerinfer_calibration']`, got
`['repair_jsonl_format']`. It also failed with
`tools.py.bak_port8188_20260923T224853`, so it predates the 2026-09-23g
port-8188 change.

## Root cause — code regression, not a stale test

2026-09-03ad established the contract that the test encodes: a failing
`_execute_plan` step becomes an `ERROR:` result and **later steps still run**
(the jsonl_repair plan then revalidates and `_jsonl_repair_summary` reports
"No file was changed … repair failed: RuntimeError: …").

Later, prompt-pack plans were added to `_execute_plan` together with an
unconditional

```
if str(result).startswith("ERROR:"):
    # Never export the old source after the revised source failed ingest.
    break
```

The reason is valid for prompt-pack plans (ingest → export / render /
production must not continue from the old source after a failed ingest), but
the guard applied to **every** plan. `jsonl_repair` is the only other
multi-step plan in `action_resolver.classify`, so it alone regressed: the
revalidation step was skipped, `len(executed) >= 2` failed, and the canned
repair summary was bypassed. No changelog entry recorded the break.

## What changed

- **`local_agent/agent.py`** `_execute_plan`: the break now fires only when
  `plan.intent.startswith("prompt_pack_")`. Other plans keep the 2026-09-03ad
  continue-after-ERROR contract. Backup:
  `agent.py.bak_planerrorbreak_20260923T225456`.
- **`local_agent/test_native_tool_calling.py`**: added
  `test_execute_plan_prompt_pack_stops_after_failed_ingest` so the prompt-pack
  stop behaviour (previously untested) is locked alongside the jsonl_repair
  continue behaviour. Backup:
  `test_native_tool_calling.py.bak_planerrorbreak_20260923T225511`.

## Evidence

- `python -m unittest test_native_tool_calling` → `Ran 104 tests … OK`
  (was 103 with 1 failure).
- `python -m unittest discover -s . -p "test_*.py"` in `local_agent/` →
  1511 tests, 20 failures, 4 errors, 16 skipped. None are in
  `test_native_tool_calling`, and none go through `_execute_plan`:
  - `worker_farm.test_farm_core` (5) — need the farm `.venv` (Celery), per
    their own failure message; `worker_farm.test_tasks_mainprocess_exceptions`
    (2) — need the repo root as cwd; `edge_gateway.test_edge_gateway` — import
    failure under discovery.
  - `test_launcher_revision` (`r98` vs `2026-09-22i-…` revision drift),
    `test_intent_mismatch` (GUI `APP_REVISION` string), `test_remote_tool_allowlist`
    (`plan_shot_reasoning` unclassified), `test_tracing` (default DB path
    written), `test_agentic_state` scope-boundary test (the turn reaches the
    model; no ActionPlan runs).
  - `test_dspy_orchestrator` / `test_generalized_video_director` /
    `test_production_integrity` hparam/POSIX-kill tests.
  These are left as-is and are outside this fix.

No GPU, ComfyUI, render, or `outputs/equal_shares/**` state was touched.
`APP_REVISION` unchanged.
