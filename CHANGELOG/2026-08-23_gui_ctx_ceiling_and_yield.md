# 2026-08-23 — UPGRADE 08: GUI context ceiling + Yield GPU button

## What changed

### local_agent/agent.py
- Added `_apply_ctx_ceiling(adaptive: int, ceiling: int | None) -> int`: returns
  `min(adaptive, ceiling)` if ceiling is set, else passes adaptive through unchanged.
  Never raises the adaptive value.
- Added `ctx_ceiling: int | None = None` keyword argument to `answer()`.
- On every hop, `adaptive_ctx` is read from `route.options()["num_ctx"]`;
  `effective_ctx = _apply_ctx_ceiling(adaptive_ctx, ctx_ceiling)` is computed and
  applied in two places:
  1. The trimmer (`_trim_context`) now receives `effective_ctx` as its `num_ctx`
     argument, so it trims to the capped window.
  2. The `oll.chat_stream` call builds `opts = route.options()` then overrides
     `opts["num_ctx"] = effective_ctx` before passing options.
- The `route` event dict is augmented with three new keys:
  `adaptive_ctx`, `effective_ctx`, `ctx_ceiling` — so the GUI can surface both
  the adaptive value and the ceiling simultaneously.
- The fallback route event (when 14B fails → 8B GPU fallback) is also augmented
  with the same three keys, computed fresh for the fallback model.

### local_agent/server.py
- Added `_parse_ctx_ceiling(value) -> int | None`: converts the GUI select value
  to int; clamps to [4096, 32768]; returns None for Auto or any invalid input.
- Added `yield_gpu() -> dict`:
  1. Returns early if `router.up(GPU_HOST)` is False.
  2. Gets resident models via `router._running_models(GPU_HOST)`.
  3. Gets the preferred model via `router._pick(gpu_tags, router.GPU_MODELS)`.
  4. Deduplicates and calls `router.unload(GPU_HOST, m)` for each.
  5. Reports freed models + VRAM via `router.gpu_memory()`.
  Reuses `router.unload()` — no second eviction path.
- Added `POST /api/yield_gpu` endpoint → calls `yield_gpu()` and returns JSON.
- `_send_turn()` now passes `ctx_ceiling=_parse_ctx_ceiling(p.get("ctx_ceiling"))`
  to `agent.answer()`.

### local_agent/static/index.html
- Added `<select id="ctxceil">` in the sidebar footer, after the Compute select.
  Options: Auto (value=""), 8 K, 16 K, 24 K, 32 K.
  Title text explains the tradeoff (lower = faster / less VRAM).
- Added `<button id="yieldgpu">` below `ctxceil`. POSTs to `/api/yield_gpu` and
  displays the result as an `actCard` (matches the existing tool-result card style).
- `ask()` now sends `ctx_ceiling` (integer or null) in every turn payload.
- `ctxceil` value is persisted to `localStorage` and restored on load.
- Route event handler: when `effective_ctx < adaptive_ctx` (ceiling is active),
  the `.who` label shows `ctx <effective> (cap <ceiling>)`; otherwise it shows
  `ctx <effective>` alone; if `effective_ctx` is absent (older server), no change.

### local_agent/test_ctx_ceiling.py (new)
- `test_apply_ctx_ceiling`: 5 cases — caps, never raises, None pass-through,
  boundary equality, small-adaptive-below-ceiling.
- `test_parse_ctx_ceiling`: 8 cases — valid values, None/empty/bogus, below-min,
  above-max, boundary values 4096 and 32768.
- Result: 13/13 OK.

### local_agent/test_yield_gpu.py (new)
- `test_yield_gpu_when_server_down`: server unreachable → freed=[], vram_mb=None,
  message mentions "not reachable".
- `test_yield_gpu_unloads_resident`: one resident model → unload called once,
  freed list contains it, vram_mb reported.
- `test_yield_gpu_nothing_to_free`: nothing resident, no preferred model →
  unload never called, freed=[], message says "Nothing".
- All mocked via `unittest.mock.patch` — no live Ollama required.
- Result: 9/9 OK.

## Why

The adaptive routing in `router.py` sets `num_ctx=20480` for the 14B primary and
`num_ctx=32768` for the 8B fallback. On a conversation that is several turns deep,
the 20K window can cause the model to load a large KV cache, making the first token
slow and competing with ComfyUI VRAM needs. The operator needed a live dial to cap
this without changing the default behaviour for short conversations.

The Yield GPU button gives the operator a one-click way to reclaim VRAM from any
Ollama model that was loaded mid-conversation but is no longer needed — typically
before starting a ComfyUI render. Previously the operator had to know to use
`ollama stop` or restart the service.

## Evidence

### Ceiling logic
```
python local_agent/test_ctx_ceiling.py
test_apply_ctx_ceiling
  ok  ceiling caps 20480 to 16384
  ok  ceiling 32768 does not raise 20480
  ok  None ceiling is pass-through
  ok  ceiling equals adaptive -> adaptive unchanged
  ok  small adaptive below ceiling is unchanged
test_parse_ctx_ceiling
  ok  16384 parses to 16384
  ok  None (Auto) -> None
  ok  empty string -> None
  ok  bogus string -> None
  ok  below 4096 -> None
  ok  above 32768 -> None
  ok  boundary 4096 is valid
  ok  boundary 32768 is valid
All OK
```

### Yield GPU logic
```
python local_agent/test_yield_gpu.py
test_yield_gpu_when_server_down   3/3 ok
test_yield_gpu_unloads_resident   3/3 ok
test_yield_gpu_nothing_to_free    3/3 ok
All OK
```

### Native function-calling regression
```
python local_agent/test_native_tool_calling.py
Ran 9 tests   OK  (0.035 s)
```

## What is still unverified

- The GUI has not been exercised end-to-end with a live agent turn using a non-Auto
  ceiling. The `ctx` label in the `.who` header will only appear after such a turn.
- The Yield GPU button result card has not been verified in a live browser session
  (the endpoint is tested via mocks, not a real GPU server).
- `localStorage` ceiling restoration on page reload is not verified against the
  browser's actual storage API (only the DOM select is confirmed present).
- `/api/yield_gpu` with a model that is mid-stream (generate loop not yet closed)
  was not tested. Ollama's `keep_alive: 0` typically waits for the active request
  to finish. This is the same behaviour as the existing GPU eviction in `decide()`.
