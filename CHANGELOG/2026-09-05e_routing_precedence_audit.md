# 2026-09-05e — Routing-precedence audit: explicit pin vs capability text-fallback

## Scope

🟢 lane. Audit only, prompted by the 2026-09-05b capability-verification
report's open question: could `classify_capability()`'s text-based
fallback silently override an explicit, non-capability model pin (e.g. a
`huihui_ai/qwen3-abliterated:14b` pin against a code-looking prompt)?

## Finding: no bug

`classify_capability()` does fall through to text classification for any
pinned model that isn't one of the three named capability models — a
Huihui-14B pin against a code-signal prompt does classify `CAP_CODE`. But
`decide()`'s `want_capability_gpu` guard requires `model is None` (or an
exact DeepSeek / Josiefied-Coder / `is_coding_model()` match) before it
acts on that classification. An explicit non-capability pin fails that
third conjunct, so the swap never runs; the pin is kept and the
classification is recorded only in `detail["capability"]`. The farm
Qwythos path has the same `model is None` requirement.

`prefer` is not the relevant gate — `prefer="gpu"` with `model=None` still
capability-routes; `prefer="auto"` with an explicit pin does not swap it.
The pin (`model=`) is what's threaded through from `server.py` →
`agent.answer()` → `router.decide()`.

One related note: `_timeshare_would_load_host_gpu()` uses the same pin
conjunct, so a Huihui pin can still trigger a GPU timeshare claim as a
GPU-resident chat model (it's in `GPU_MODELS`) — that loads Huihui, not
Coder. Not a bug, just worth knowing the timeshare and capability paths
share this guard shape.

## What shipped

New regression test only:
`CapabilityDecideTests.test_explicit_huihui_pin_not_overridden_by_code_signal`
in `local_agent/test_capability_routing.py`. Locks the contract so a future
edit to `want_capability_gpu`'s conjuncts can't silently regress this.
Full suite: 18 tests, OK.

## What was not changed

No router fix — none was needed. `classify_capability()`'s fall-through
behavior is unchanged and is fine as long as `decide()` keeps gating on it
correctly, which the new test now enforces.

## Next

Task #46 (reconcile the Coding-mode picker pin vs auto capability routing)
queued next on this lane.
