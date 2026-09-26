# Claude Code prompt — GUI context ceiling + "Yield GPU" button (refreshed 2026-08-23)

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/README.md`, `CLAUDE.md`,
`local_agent/router.py`, `local_agent/agent.py`, and `local_agent/server.py` first.
**Do not touch the render pipeline, the busy-detection signals, or
`outputs/equal_shares/**`.**

## What changed since the original 08 — read this first

`num_ctx` is no longer a single hard-coded value. The adaptive reasoning pair now
sets it **per model** in `router.Decision.options()`: the 14B primary gets 20480,
the 8B fallback gets 32768, and there is predictive 14B→8B routing at ~16K
estimated tokens. So the GUI control must be a **ceiling that coordinates with**
that logic — never a blanket override that fights it.

## Feature 1 — a GUI context ceiling (num_ctx)

The operator wants to cap how much context the agent uses, live, from the chat
interface, without editing code or restarting.

1. **Control in `local_agent/static/index.html`** — a select of presets
   (`8192 / 16384 / 24576 / 32768`) plus an "Auto" default, labelled "Context
   (tokens)". Persist the choice in `localStorage`, restore on load, show the value
   actually in effect.
2. **Send it each turn** (match how `server.py` already receives `message`/`prefer`).
3. **Apply as a CEILING, after the adaptive value is computed.** Thread the value
   into `agent.answer(...)`. The effective num_ctx for a turn is
   `min(adaptive_value_from_Decision.options(), gui_ceiling)` when the operator set
   one, else the adaptive value unchanged. Never raise num_ctx above what the
   chosen model/tier already allows. "Auto" means: don't cap — use the adaptive
   value as-is.
4. **Clamp** the incoming value to `[4096, 32768]`; a bogus value never crashes a
   turn — fall back to Auto.
5. **Surface the effective value** on the existing `route` event so the GUI line can
   show e.g. `[GPU qwen3-abliterated:14b · ctx 20480 (capped 16384)]`.
6. **One line of UI helper text**: a lower ceiling frees VRAM for a render and can
   push a long chat to the 8B sooner; Ollama reloads the model when num_ctx changes,
   so the first reply after a change is slower. Do not invent numbers.

Interaction to respect, not re-implement: the predictive 14B→8B switch at ~16K
tokens and the reactive OOM failover already live in `router`/`agent`. The ceiling
only *lowers* the window; it must not disable or duplicate that routing.

## Feature 2 — a manual "Yield GPU" button

Reuse `router.unload()` — do not write a second eviction path. Add a thin action
that finds the resident GPU model the way `router.decide()` does
(`router._pick(router._tags(GPU_HOST), GPU_MODELS)` when `router.up(GPU_HOST)`; also
evict anything `router._running_models(GPU_HOST)` reports resident), calls
`router.unload(GPU_HOST, model)`, and reports what it freed. Expose it as a GUI
"Yield GPU" button hitting a new endpoint. Safe to press when nothing is resident
("nothing to free"). Report VRAM via `router.gpu_memory()` if available but never
block on `nvidia-smi`. It never starts/stops a render and never touches
`render_queue_owner.json`.

## Constraints

Stdlib only; server stays on `127.0.0.1`; `agent.answer()` stays
transport-agnostic (the ceiling is a plain optional argument). Never weaken
`gpu_busy()` or the one-owner rule.

## Verify (show commands + output; mockable)

1. `python local_agent/test_native_tool_calling.py` and `test_router_switching.py`
   → still green.
2. New stdlib test: with the adaptive value mocked at 20480, a GUI ceiling of 16384
   yields an effective 16384; a ceiling of 32768 leaves 20480 unchanged (never
   raised); "Auto" passes the adaptive value through; out-of-range clamps to Auto.
3. New stdlib test: the Yield endpoint calls `router.unload(GPU_HOST, <model>)` once
   for the resident model and returns "nothing to free" when `up(GPU_HOST)` is False.
4. Manually: change the ceiling, send a turn, confirm the effective value shows in
   the route line; press Yield with and without a model resident.

## Record it

Write `CHANGELOG/<today>_gui_ctx_ceiling_and_yield.md` (what/why/evidence/verified/
unverified), add its row to `CHANGELOG/README.md`, mark UPGRADE 08 built in
`local_agent/UPGRADE/00_INDEX.md`, and note both controls in
`local_agent/README.md`. State plainly that the control is a ceiling coordinating
with the adaptive pair, not a replacement for it.
