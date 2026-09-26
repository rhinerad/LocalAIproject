# ChatGPT / Codex prompt — dynamic 14B↔8B chat-model fallback on a 16 GB GPU

Paste this whole block into ChatGPT (Codex) or Claude Code. Run it from the repo
root of the local agent (`COMFYUI_STORY_HANDOFF_2026-08-09/`).

---

You are editing a **custom Python script**, not a framework — the offline assistant
under `local_agent/` (stdlib only, no LangChain/AutoGen, Ollama as the backend on
`127.0.0.1`). Read `local_agent/README.md`, `local_agent/router.py`,
`local_agent/agent.py`, and `local_agent/ollama_client.py` before changing
anything. Do not touch the render pipeline or `outputs/equal_shares/**`.

## Goal

The agent's GPU **chat/reasoning** tier must dynamically choose between a 14B and an
8B abliterated model so a growing context never OOMs the 16 GB card, while short
prompts still get the smarter 14B. This is the chat model only — it is separate
from the vision watcher (that has its own tiering) and from the GUI num_ctx control.

### Why (16 GB VRAM budget)

- A 14B model at Q4 is ~9 GB of static VRAM. The OS/display take 1–2 GB.
- KV cache grows with history: at ~32K context it can add 4 GB+, pushing a 14B
  past 16 GB. Ollama then silently offloads layers to system RAM and generation
  crawls — a slowdown, not a clean failure. So **predict and route before sending**,
  and keep a reactive catch as a backstop.

## Step 1 — install the two models (internet is available now)

    ollama pull huihui_ai/qwen3-abliterated:14b     # ~9.0 GB, Q4_K_M — primary reasoning
    ollama pull huihui_ai/qwen3-abliterated:8b      # ~5.0 GB, Q4_K_M — fallback (small weights leave room for a big KV cache)

Confirm both load and answer:

    ollama run huihui_ai/qwen3-abliterated:14b "say ok"
    ollama run huihui_ai/qwen3-abliterated:8b  "say ok"

(The operator asked for `huihui-ai/Qwen3-8B-abliterated`; that is the Hugging Face
repo id. The Ollama tag above is its equivalent. If you prefer higher fallback
quality over headroom, use `:8b-q8_0` (~8.7 GB) instead — but Q4 is the safer
fallback because the point of falling back is to free VRAM for the KV cache.)

Wire them in as the **GPU chat preference**, ahead of the current entries, in
`router.py`'s `GPU_MODELS` (keep the existing ones as later fallbacks so nothing
breaks if a pull is missing):

    GPU_MODELS = ["huihui_ai/qwen3-abliterated:14b", "huihui_ai/qwen3-abliterated:8b",
                  "equal-shares-gpu", "equal-shares", "qwen2.5-coder:14b", ...]

Define the pair as named constants so the routing logic and the model list share one
source of truth:

    GPU_PRIMARY_MODEL  = "huihui_ai/qwen3-abliterated:14b"
    GPU_FALLBACK_MODEL = "huihui_ai/qwen3-abliterated:8b"

## Step 2 — Strategy 1: predictive context-length routing (primary mechanism)

Before each GPU turn, estimate the prompt's token count and pick the model:

- Add a token estimator (stdlib, no downloads). A conservative
  `estimate_tokens(messages) -> int` — sum the characters of every message's content
  (and note images add a fixed per-image cost) and divide by ~3.5, rounding up — is
  enough; label it an estimate, not exact. Do **not** add a tokenizer dependency.
- Add `DYNAMIC_SWITCH_TOKENS = 16000` as a tunable constant, with a comment tying it
  to the budget: 14B Q4 (~9 GB) + OS overhead leaves roughly 5–6 GB for KV; ~16K
  tokens is where a 14B KV cache starts to threaten the 16 GB ceiling.
- In `router.decide()` (or a helper it calls), when the tier is **GPU** and both the
  primary and fallback are installed: if `estimate_tokens(history) > DYNAMIC_SWITCH_TOKENS`
  choose `GPU_FALLBACK_MODEL`, else `GPU_PRIMARY_MODEL`. If only one is installed,
  use it. CPU tier is unchanged. Record the choice and the estimate on the
  `Decision` (e.g. `detail["dynamic"] = {"est_tokens": N, "picked": model, "threshold": 16000}`)
  so the GUI route line can show it.
- Coordinate with num_ctx: when the 14B is chosen, cap its `num_ctx` so the KV cache
  cannot blow the budget (e.g. clamp to ≤ 16384 unless the operator's GUI value is
  lower); the 8B may use a larger `num_ctx`. Keep honoring the GUI num_ctx control
  as the ceiling, not a floor.

## Step 3 — Strategy 2: reactive fallback (backstop)

Wrap the model call in `agent.answer()` (and `draft_prompt()`), so a load/OOM/timeout
on the primary transparently retries the **identical** prompt on the fallback:

- Catch `OllamaUnavailable`, HTTP 500 from `/api/chat`, load failures, and timeouts.
- On catch: emit a `note` event ("14B unavailable/over VRAM — retrying on 8B"),
  `router.unload(GPU_HOST, GPU_PRIMARY_MODEL)` to free the card, then re-issue the
  same messages against `GPU_FALLBACK_MODEL` once. If the fallback also fails, surface
  a clean `error` — never a stack trace.
- Only one downgrade step (14B → 8B), never a loop. If already on the 8B, do not
  retry the 8B against itself.

## Step 4 — model lifecycle (avoid VRAM contention between the two)

- Do not keep both resident. Before loading the fallback, unload the primary
  (`keep_alive:0` via the existing `router.unload`). Set a short `keep_alive` on chat
  requests (e.g. via options) so the inactive model releases VRAM quickly and the
  other can load — consistent with the project's one-inference-model-at-a-time rule.
- The existing render-yield behavior stays: a live render still forces the CPU tier
  and evicts any resident GPU model. This feature only changes *which* GPU chat model
  is chosen when the GPU is free.

## Constraints

- Stdlib only; no tokenizer or framework dependency. Server stays on `127.0.0.1`.
- `agent.answer()` stays transport-agnostic (history list + callback).
- Never weaken `gpu_busy()` / the "unknown GPU = busy" fail-safe. One GPU owner ever.

## Verify before claiming done (show commands + output)

Mockable, no live GPU needed:

1. `python local_agent/test_native_tool_calling.py` → still green.
2. New stdlib test (mock `router._tags` so both models look installed, and patch
   `estimate_tokens`): history under the threshold routes to the 14B; history over it
   routes to the 8B; only-one-installed routes to that one; CPU tier unaffected.
3. New stdlib test: patch the model call to raise on the primary and succeed on the
   fallback — `agent.answer()` emits the `note`, calls `unload` on the primary, and
   returns the fallback's reply; a primary success never triggers a downgrade.

Live checks to hand back to the operator (need real Ollama/GPU — mark unverified):
both pulls succeed and answer; a long (>16K-token) conversation actually loads the 8B
and a short one loads the 14B (watch `ollama ps` and the GUI route line); forcing the
14B to OOM triggers the reactive downgrade with generation still completing on the 8B.

## Record it (mandatory)

Write `CHANGELOG/<today>_dynamic_model_fallback.md` in the same session — the five
required answers (what/why/evidence/verified-after/still-unverified) with the test
output pasted — then add its row to `CHANGELOG/README.md` and note the new models and
routing in `local_agent/README.md`.
