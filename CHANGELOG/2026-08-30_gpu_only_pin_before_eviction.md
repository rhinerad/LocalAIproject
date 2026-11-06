# 2026-08-30 — GPU-only pins must not become CPU when eviction is unverified

## What changed

`local_agent/router.py` `decide()` ran the busy-GPU eviction-verification block
(the early `Decision(tier="cpu", model=None, ... eviction could not be verified)`)
**before** `is_powerinfer_model(model)` and `is_gpu_only_opt_in_model(model)`.

Those later checks exist so a pinned Heretic or PowerInfer chat refuses with
`tier="gpu", model=None` and "will not fall back to CPU" — never Huihui 8B, never
a CPU Decision. The eviction block returned that CPU Decision first whenever
`/api/ps` could not confirm Ollama VRAM was released.

Moved both GPU-only pin checks **above** the eviction early-return. Eviction
still gates ordinary CPU hand-off. A GPU-only pin never uses the CPU tier, so
it must not wait on, or inherit, that CPU refusal.

| File | Change |
|---|---|
| `local_agent/router.py` `decide()` | PowerInfer + GPU-only opt-in branches run before `evict_gpu_residents()` early-return. |
| `local_agent/test_router_switching.py` | Two regression tests: busy + unverified eviction + Heretic pin; same for PowerInfer. Both require `tier="gpu", model=None` and `evict_gpu_residents` not called. |

Did not touch `tools/powerinfer/`, `work/`, `vault.py`, or `pipeline_lib.py`.

## Why

`CHANGELOG/2026-08-29k_powerinfer_chat_picker.md` recorded
`python test_router_switching.py -v` as `Ran 36 tests in 8.071s` / `OK`.
Re-running that suite from `local_agent/` today failed:

`test_heretic_pin_refuses_while_busy_without_cpu_substitution` (line 166)
expected `tier="gpu", model=None, "will not fall back to CPU"`.
`decide()` returned `tier="cpu"` from the unverified-eviction path instead.

That is the silent Huihui/CPU substitution the comment under the Heretic
branch forbids. Same order bug for PowerInfer.

## The evidence

Before the reorder, the failing assertion was the Heretic busy-pin test.
After:

```
python test_router_switching.py -v
...
test_gpu_only_opt_in_pin_refuses_when_busy_even_if_eviction_unverified ... ok
test_heretic_pin_refuses_while_busy_without_cpu_substitution ... ok
test_powerinfer_pin_refuses_when_busy_even_if_eviction_unverified ... ok
...
Ran 38 tests in 6.972s
OK
```

38 = the previous 36 plus the two new eviction-unverified pin tests. The
original 36, including the previously failing Heretic test, all pass.

Same `decide()` surface, re-run after the reorder:

```
python test_router_status_busy.py -v
Ran 3 tests in 0.415s
OK

python test_powerinfer_chat_route.py -v
Ran 5 tests in 0.001s
OK

python test_powerinfer_openai_proxy.py -v
Ran 5 tests in 0.000s
OK

python test_native_tool_calling.py -v
Ran 28 tests in 26.729s
OK
```

`test_unverified_gpu_eviction_refuses_cpu_handoff` still passes: a primary
(not GPU-only) pin while busy with unverified eviction is still a CPU Decision
with `model is None`. That path is unchanged.

## What was verified after

The five suites above. No live GPU load, no `server.exe`, no ComfyUI, no
Heretic create.

## What is still unverified

- A live GUI pin of Heretic or `powerinfer-local` while ComfyUI owns port 8188
  and GPU Ollama `/api/ps` is actually unreadable.
- Whether a PowerInfer pin that already owns the GPU should still *attempt*
  Ollama eviction as a courtesy. This change skips eviction for those pins
  because they never take the CPU hand-off the eviction lock exists to protect.
