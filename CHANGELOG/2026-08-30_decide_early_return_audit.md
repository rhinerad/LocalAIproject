# 2026-08-30 — decide() early-return audit after the GPU-only pin reorder

## What changed

Nothing in `decide()`. This entry is the end-to-end walk that
`2026-08-30_gpu_only_pin_before_eviction.md` asked the next session not to
redo from scratch.

Audited: `local_agent/router.py` `decide()` (current order after today's
eviction-before-pin fix). No further instances of that bug class were found
**before** the `is_powerinfer_model()` / `is_gpu_only_opt_in_model()` checks.
No speculative restructure.

## Why

Two GPU-only pins (Heretic and PowerInfer) were the same ordering bug: an
earlier `Decision(tier="cpu")` short-circuited a later pin check that is
supposed to win with `tier="gpu", model=None`. That is a pattern. Walking
every return once is cheaper than finding the next instance during a feature
add.

## The evidence — every `decide()` return, in execution order

Setup that is **not** a return, but runs **before** the pin checks:

| Step | What it does | Before/after pin checks | Same-bug candidate? |
|---|---|---|---|
| `gpu_busy()` | fills `busy`, `why`, `detail` | before | no — no `Decision` |
| CPU `/api/tags` | `cpu_have` | before | no |
| `skip_gpu_inventory` | if busy **and** Huihui 8B is on CPU, set `gpu_have = []` and skip GPU `/api/tags` | before | no — not a return. Heretic/PowerInfer busy paths do not use `gpu_have`. Idle Heretic still inventories GPU because `busy` is false. |

Pin checks (these **are** the checks that must win):

| Return | Condition | Decision | Before/after itself |
|---|---|---|---|
| PowerInfer, foreign GPU owner | `is_powerinfer_model` and busy and not PowerInfer-owned | `tier="gpu"`, host=proxy, `model=None`, "will not fall back to Ollama or CPU" | **is** the pin check |
| PowerInfer, `prefer=="cpu"` | pin + CPU preference | `tier="gpu"`, `model=None`, will not fall back to CPU | pin check |
| PowerInfer, proxy/backend down | pin + not ready | `tier="gpu"`, `model=None`, explicit down reason | pin check |
| PowerInfer, ready | pin + GPU free or PowerInfer already owns it | `tier="gpu"`, model=alias, backend=powerinfer | pin check |
| Heretic busy | `is_gpu_only_opt_in_model` and busy | `tier="gpu"`, `model=None`, "will not fall back to CPU" | pin check |
| Heretic `prefer=="cpu"` | pin + CPU preference | `tier="gpu"`, `model=None` | pin check |
| Heretic, GPU Ollama down | pin + `not up(GPU_HOST)` | `tier="gpu"`, `model=None` | pin check |
| Heretic not installed | pin + missing tag | `tier="gpu"`, `model=None` | pin check |
| Heretic success | pin + GPU free + installed | `tier="gpu"`, model=selected | pin check |

Returns **after** the pin checks (GPU-only / PowerInfer pins never reach these
when `is_*` matches):

| Return | Condition | Decision | Covered? |
|---|---|---|---|
| Unverified eviction | `busy and ensure_gpu_evicted` and `/api/ps` not verified | `tier="cpu"`, `model=None`, "eviction could not be verified" | `test_unverified_gpu_eviction_refuses_cpu_handoff` (primary pin). The GPU-only gap here was the bug fixed today: `test_gpu_only_opt_in_pin_refuses_when_busy_even_if_eviction_unverified`, `test_powerinfer_pin_refuses_when_busy_even_if_eviction_unverified`, plus the original Heretic busy test. |
| Unknown / unavailable pin | `model not in allowed`, not primary, not coding-with-fallback | `tier="cpu"`, `model=None`, "Selected chat model is unavailable" | coding fallback: `test_unknown_coding_model_falls_back_cleanly`. Generic unknown pin: no dedicated GPU-only test (those pins never reach this). |
| GPU success | `want_gpu` and GPU up and a selected model | `tier="gpu"` | idle-path tests (Heretic 8k ctx, coding idle, short primary, …) |
| Final return | everything else | **always** `tier="cpu"` (paired 8B, coding-on-CPU, or `model=None` "cannot run now") | busy primary → 8B: several tests. GPU_MODELS-only busy pin: `test_gpu_only_pin_refuses_instead_of_substituting_when_busy` (asserts `model is None` and "cannot run now"; does **not** assert `tier="gpu"`). |

### Candidate set (branch fires **before** the pin checks and does not account for a pin)

**Empty.** After today's reorder there is no `return Decision(...)` above
`is_powerinfer_model` / `is_gpu_only_opt_in_model`.

`skip_gpu_inventory` is the only pre-pin control-flow of interest. It cannot
emit a CPU Decision. Scenario that would have been a candidate if it returned:
Heretic pinned + GPU busy + 8B on CPU → inventory skipped. Actual outcome
today: the Heretic busy refusal still runs next. Covered by
`test_heretic_pin_refuses_while_busy_without_cpu_substitution`.

### Related, but not the same contract — left untouched

`test_gpu_only_pin_refuses_instead_of_substituting_when_busy` uses a
`GPU_MODELS`-only tag (`gpu-only:latest`), **not** `GPU_ONLY_OPT_IN_MODELS`.
That path is after the pin checks. It currently returns `tier="cpu"` with
`model=None` and "cannot run now". If eviction is unverified, the eviction
CPU Decision fires first instead of "cannot run now". Both are CPU refusals
with no model; the dedicated Heretic/PowerInfer contract (`tier="gpu"`, "will
not fall back to CPU") does not apply to that test. Treating `GPU_MODELS`-only
pins like Heretic would be a product change, not today's reorder. Stopped.

Exact-string pin match (`"gpt-oss-20b-heretic"` / `POWERINFER_MODEL_ALIAS`)
means a `:latest` suffix would miss the pin checks and fall through to the
generic unavailable/CPU path. No evidence the picker emits those strings.
Stopped rather than inventing alias policy.

## What was verified after

No source change. Re-ran from `local_agent/`:

```
python test_router_switching.py -v
Ran 38 tests in 7.419s
OK
```

38 is the post-fix suite (36 from 2026-08-29k plus the two eviction-unverified
pin tests). `test_heretic_pin_refuses_while_busy_without_cpu_substitution` is
`ok`.

## What is still unverified

- Live GUI pin of Heretic or PowerInfer while ComfyUI owns 8188 and GPU
  Ollama `/api/ps` is unreadable (same as the previous entry).
- Whether a `GPU_MODELS`-only pin should get the Heretic-style `tier="gpu"`
  refusal. Existing test does not require it.
