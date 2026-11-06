# 2026-09-05v — GPU timeshare audited across every routed model: no bugs

## Scope

🔵 lane, Task #41. Audit only, no production change.

## Finding: clean across the board

Idle-8188 timeshare behavior matches the 2026-09-05e/j contracts for
every routed pin/tier. Key structural clarification: `_timeshare_would_load_host_gpu()`
is only the host-GPU conjunct — the farm-skip branch in
`_maybe_comfy_timeshare()` (`model is None` + `CAP_TOOL` + farm reachable)
is a separate, earlier check that never consults that conjunct. So an
unpinned tool prompt always evaluates `would_load_host_gpu=True`, but
takes the farm path (no `/free`) when the farm is up, and only claims/
loads Huihui-14B when the farm is down — that's the designed split, not a
leak.

Also clarified: PowerInfer is a real host-GPU load (`server.exe` on the
5080) and does claim via timeshare, confirmed by code, the 2026-09-04z
live verify, and an existing test. What PowerInfer skips is only the
sidebar `gpu_gate` prompt (`timeshare_claim_needs_sidebar_gate` returns
False) — the task prompt's framing of PowerInfer as "should skip
timeshare like CPU" was the wrong expectation, not a bug.

Full per-pin matrix (14 rows: unpinned default, Huihui-14B pin,
Huihui-8B fallback, Coding-mode pin, unpinned CAP_CODE, DeepSeek pin,
unpinned CAP_LOGIC, `gpt-oss-20b-heretic`, PowerInfer, unpinned-tool+farm,
Qwythos pin, CPU pin, `prefer=cpu`, other coder tags) all matched the
contract. 18/19 automated matrix cases matched on first run; the 19th
(unpinned-tool+farm) was a bad test-script expectation, not a code
defect — corrected, not a fix.

## Tests / live

116/116 existing tests still pass
(`test_router_comfy_timeshare`, `test_capability_routing`,
`test_agent_timeshare_gpu_gate`, `test_router_switching`). Live spot
check: port 8188 was closed and `nvidia-smi` showed 8441 MiB
(`llama-server.exe`) during this pass, so no live idle-8188 claim was
exercised this round (starting ComfyUI was out of scope) — skip-path
`decide()` for Qwythos/CPU/`prefer=cpu` confirmed `n_clears=0` live, and
conjunct values matched the table on the live interpreter. Prior live
`/free` evidence for Huihui and PowerInfer (2026-09-04z) still stands;
Heretic/DeepSeek/Josiefied idle-8188 claims were verified on the mocked
path only this pass, not re-run live.

## What shipped

Nothing — no bugs found, no regression tests added. Coverage note only:
Heretic and DeepSeek idle-8188 `decide()` had no named test before this
audit; they behaved correctly, so no test was added for a gap that isn't
a mismatch.

## Task #41 closed

All three tasks originally gating this (#39, #40) plus this audit itself
are now resolved. GPU/ComfyUI timeshare is considered fully verified
across the current model roster.
