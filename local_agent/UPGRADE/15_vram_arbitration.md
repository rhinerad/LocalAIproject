# Claude Code / Codex prompt — VRAM arbitration so media jobs never get stuck behind the chat LLM

> **Source preserved from Google Drive (2026-08-24):**
> [`15_vram_arbitration.md`](https://docs.google.com/document/d/1PJOklNvegWbcGrHplksk0_5C6YbnpYcg41hu_tJM8UA/edit?usp=drivesdk).
> This local file is the checked-in working copy; see
> [`DRIVE_SOURCE_MANIFEST.md`](DRIVE_SOURCE_MANIFEST.md) for related sources.

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/router.py`,
`local_agent/media_watcher.py`, `local_agent/media_queue.py`,
`local_agent/capabilities.py`, and `local_agent/agent.py` first. Stdlib only; server
on `127.0.0.1`. **Do not touch the render pipeline or `outputs/equal_shares/**`.**

## The problem to fix

Today the media watcher (UPGRADE 09) loads the largest vision tier that fits **free**
VRAM, and if none fits it leaves the job pending. But the chat LLM (the adaptive 14B,
~9 GB + KV cache) can be resident and holding the card, so on a 16 GB RTX 5080 the
vision 8B (~10 GB) never fits — and the queued image/video/audio job **waits forever**.
Nothing currently makes the chat model yield to a queued media job.

## The rule to add

**A queued media job must never be blocked solely because the chat LLM holds VRAM.**
A render still always wins; this is only about arbitrating between the chat model and
the media watcher when *no render* owns the GPU.

Reclaim ladder, tried in order until the job can run:

1. **Coexist.** Keep the chat model resident; load the largest vision tier
   (`capabilities.vision_tiers()`) that fits current `router.gpu_free_mb()`. (Current
   09 behavior.)
2. **Downgrade the chat model.** If nothing fits, and the resident chat model is the
   **primary 14B**, unload it and (a) let the next chat turn come back on the **8B**
   for the duration, then re-check fit for the largest vision tier. Prefer this — it
   keeps chat available, just smaller.
3. **Fully evict chat.** If a vision tier still will not fit alongside the 8B, unload
   the chat model entirely (`router.unload(GPU_HOST, <resident>)` for whatever
   `router._running_models(GPU_HOST)` reports), run the job on the largest vision tier
   that now fits full VRAM, and let chat reload at its normal adaptive size on the
   operator's **next** message.
4. Run the job; when the pending media batch drains, release the vision model
   (`keep_alive:0`) so chat can reload cleanly.

Guarantees: after this, there is **always** a path to run a queued media job when the
GPU is free of renders. A job only stays pending for (a) a render owning the card, or
(b) genuinely not enough total VRAM for even the smallest vision tier with chat fully
evicted — which on 16 GB should not happen for the 4B tier.

## Coordination rules (avoid thrash and mid-turn interruption)

- **Never interrupt an in-flight chat generation.** If a chat turn is streaming, the
  watcher waits for it to finish (it is short), then reclaims. Use a lightweight
  shared signal — e.g. a `chat_busy` flag/file the agent sets around a turn, or check
  `router._running_models` plus a recent-activity timestamp — so the watcher only
  evicts an **idle** resident chat model.
- **Batch the VRAM window.** When the watcher does reclaim, drain the whole pending
  media batch in that one window before releasing — do not evict chat, run one item,
  reload chat, and immediately evict again. One reclaim → many items → release.
- **Cooldown.** After releasing back to chat, wait one poll before reclaiming again so
  a chatting operator is not starved by a trickle of media jobs.
- **Signal the pending pressure.** When media jobs are waiting on VRAM, set a flag the
  router reads so the **next** chat turn prefers the 8B (reuse the existing predictive
  path — it already knows how to pick the 8B). This makes room cooperatively instead of
  only by force.
- UPGRADE 12's short `keep_alive` on non-interactive calls (if built) already helps
  chat release VRAM on its own — this builds on that, it does not replace it.

## Where it lives

- Put the fit/eviction decision in one helper (e.g. `router.plan_vision_vram(tiers)`
  or a small function in `media_watcher`) that returns `(vision_tier, chat_action)`
  where `chat_action ∈ {none, downgrade, evict}`. One source of truth so the watcher
  and any future caller agree.
- The watcher applies `chat_action` (unload the resident chat tag as needed), loads
  the chosen vision tier, processes, and on batch-drain releases the vision model.
- Reflect the reason in the queue's **waiting-on** text (UPGRADE 14, if built):
  e.g. "waiting for the chat model to free VRAM" vs "waiting for a render".

## Constraints

- One GPU owner vs a render is unchanged: a render (queue owner / port 8188) always
  wins; the watcher never evicts a render, only the chat model.
- `router` stays the authority on GPU state and unloading; do not add a second
  eviction path. `agent.answer()` stays transport-agnostic.
- Never delete queued jobs or source media. Fail-safe on unknown GPU state (treat as
  "cannot fit" and wait) exactly as elsewhere.

## Verify (stdlib, mockable — show output)

1. Existing suites green; `validate_h3_prompt.py` 124/124.
2. New tests with `router.gpu_free_mb`, `_running_models`, `gpu_busy` mocked:
   - 14B resident, free VRAM too low for any vision tier, no render →
     `plan_vision_vram` returns `chat_action=downgrade` (or `evict`) and a runnable
     vision tier; the watcher calls `unload` on the resident chat tag and then loads
     vision.
   - a render owning the card → `chat_action=none`, job stays pending (render wins).
   - chat model marked busy/streaming → watcher does NOT evict; waits.
   - enough free VRAM → `chat_action=none`, coexist (no eviction).
3. Anti-thrash: two queued jobs drain in a single reclaim window (one eviction, not
   two).

## Record it

Write `CHANGELOG/<today>_vram_arbitration.md` (what/why/evidence/verified/unverified),
add its row to `CHANGELOG/README.md`, and document the reclaim ladder in
`local_agent/README.md`. State the live-unverified part plainly: the real 14B-resident
→ downgrade → vision-runs sequence needs a live GPU to confirm.
