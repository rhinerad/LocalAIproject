# 2026-11-05c — the routing test suites no longer depend on the machine's `EQUAL_SHARES_*` overrides or its GPU

Closes the "12 FAIL" item carried as out of scope since `2026-11-04a` section 3.
Branch `claude/jolly-dirac-9impbq`. Id claimed with `scripts/next_changelog_id.py`.

## 1. Cause

`router.py` reads `EQUAL_SHARES_PRIMARY_REASONING_MODEL`,
`EQUAL_SHARES_FALLBACK_REASONING_MODEL`, the coding/DeepSeek/Qwythos tags, the
two Ollama hosts and the PowerInfer settings **once, at import**, into module
constants. The workstation sets
`EQUAL_SHARES_PRIMARY_REASONING_MODEL=gpt-oss-20b-heretic:latest`
machine-wide. Under that override the "primary" of the Huihui 14B/8B pair is
the GPU-only opt-in model, so every test about the pair's semantics (paired
8B CPU fallback, predictive 14B→8B demotion, media-pressure demotion, legacy
`-v2` pin, busy-picker ordering, VRAM-derived `num_ctx`) asserts one thing
and the router does another. Reproduced in this Linux session by exporting
the same variable: `test_router_switching` 13 failures (11 of them this),
`test_router_status_busy` 1, and `test_gpu_vram_num_ctx` 3 of 7, which the
workstation runs had not covered.

The tests describe the shipped defaults. A deployment override is not a test
input, so the fix is isolation, not rewriting the assertions.

## 2. Change

- New `local_agent/testsupport_env.py`: `isolate_model_env()` pops the 21
  `EQUAL_SHARES_*` / `POWERINFER_*` variables that `router.py` and
  `ollama_client.py` read at import, and, only if one was actually set **and**
  the module was already imported (a batch run where another suite imported
  `router` first), reloads `router` and `ollama_client` in place so existing
  references see the defaults. Idempotent; returns the names it removed.
  Nothing outside the tests imports it. The name deliberately does not match
  `test_*.py` so discovery does not pick it up as a suite.
- `test_router_switching.py`, `test_router_status_busy.py`,
  `test_gpu_vram_num_ctx.py`: call it before `import router`.
- `test_router_switching.py`, two coding-mode tests: a coding pin takes the
  capability-GPU path, which calls the live `thermal_blocks_gpu()` and
  `queue_owner()`. Neither was patched, so the tests needed a real
  `nvidia-smi` and a cool card: they passed on the workstation and failed on
  every machine without a GPU (the last 2 of this session's 4 "known"
  failures). Both now patch `thermal_blocks_gpu` → `None`, `queue_owner` →
  released, and (for the selecting test) `prepare_gpu_model` → verified, the
  same way `_pinned_14b_gpu()` in the same file already does.

No production code changed.

## 3. Evidence (this Linux session, Python 3.13)

With `EQUAL_SHARES_PRIMARY_REASONING_MODEL=gpt-oss-20b-heretic:latest`
exported, exactly as on the workstation:

    python test_router_switching.py      Ran 54 tests ... OK   (was FAILED (failures=13))
    python test_router_status_busy.py    Ran 8 tests ... OK    (was failures=1)
    python test_gpu_vram_num_ctx.py      Ran 7 tests ... OK    (was failures=3)
    python -m unittest -q test_router_status_busy test_router_switching test_gpu_vram_num_ctx
                                         Ran 69 tests ... OK
    # reload path: an un-isolated router importer first
    python -m unittest -q test_vram_arbitration test_gpu_vram_num_ctx test_router_status_busy test_router_switching
                                         Ran 74 tests ... OK
    # extra overrides on top (fallback tag, GPU host, coding tag)
    python -m unittest -q test_router_status_busy test_gpu_vram_num_ctx   Ran 15 tests ... OK

Without the override (baseline) the same three suites are OK, so nothing was
masked. `isolate_model_env()` reports `['EQUAL_SHARES_PRIMARY_REASONING_MODEL']`
on first call and `[]` on the second; `router.PRIMARY_REASONING_MODEL` goes
from the override to `huihui_ai/qwen3-abliterated:14b`. The gateway suite
stays at 64 OK.

The two coding tests' earlier failure on this box is confirmed as the thermal
guard: `router.thermal_blocks_gpu()` returns `thermal telemetry unavailable
(nvidia-smi not found ...)` here, which the unpatched tests turned into a CPU
decision.

## 4. Unverified / next

- Not run on the workstation yet. Expected there: `test_router_switching`
  `Ran 54 ... OK`, `test_router_status_busy` `Ran 8 ... OK`,
  `test_gpu_vram_num_ctx` `Ran 7 ... OK`, with the machine-wide override
  still set and untouched.
- Other suites in `docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md` that import
  `router` were checked under the override here: `test_activity_trace`,
  `test_agent_timeshare_gpu_gate`, `test_auto_farm_routing`,
  `test_intent_mismatch`, `test_launcher_kv_cache`,
  `test_measure_ollama_kv_cache`, `test_tracing`, `test_powerinfer_chat_route`,
  `test_vram_arbitration`, `test_ollama_context_options` are OK with and
  without it. `test_capability_routing` (14 errors), `test_native_tool_calling`
  (1), `test_router_comfy_timeshare` (2) fail here identically with and
  without the override, so they are box-specific (no GPU, no ComfyUI, no
  Windows), not this bug, and were not touched.
