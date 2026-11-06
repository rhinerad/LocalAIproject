# Claude Code prompt — diagnose & fix "agent only uses CPU models"

Paste into Claude Code. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/router.py`,
`local_agent/START_LOCAL_AGENT_GUI.ps1`, `local_agent/static/index.html`,
`local_agent/server.py`, and `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md` first.
**Stdlib only; 127.0.0.1 only; never start, resume, or monitor a render/ComfyUI; do
not touch `outputs/equal_shares/**`.**

## Symptom

The desktop agent is serving replies from the **CPU** `huihui_ai/qwen3-abliterated:8b`
even though the GPU primary `huihui_ai/qwen3-abliterated:14b` is installed. Likely cause
(confirm, do not assume): a ComfyUI backend was holding **port 8188** + VRAM, so
`router` correctly routed to CPU to protect the card — and by design it does **not** poll
the GPU Ollama catalogue while 8188 is owned. That stalled workflow was already stopped
(`CHANGELOG/2026-08-25_stalled_comfyui_workflow_stopped.md`), so GPU routing should now
be available. Find out why it still isn't, and fix the real cause.

## Step 1 — diagnose live (report findings before changing anything)

Run and capture:

1. Is anything listening on **8188**? (`router.comfy_listening()` / a socket check.)
2. `router.gpu_memory()` / `nvidia-smi` — is VRAM at idle baseline, or is ~12 GB still
   allocated by a leftover process?
3. Is the **GPU** Ollama server up on `:11434` (`router.up(GPU_HOST)`), and does its
   catalogue actually contain the 14B (`router._tags(GPU_HOST)`)?
4. What does `router.decide()` return right now — tier, model, and the **reason** string
   in its detail? Run `python local_agent\router.py` and paste the output.

From those four, state the true cause. It will be one of:
- (A) 8188 still listening / VRAM still held → **working as designed**, GPU is genuinely
  busy. Fix = visibility (Step 3) + confirm it recovers when 8188 clears.
- (B) 8188 clear and GPU idle, but the GPU server is **down** or the 14B is **not in the
  GPU catalogue** → real gap: the model/server isn't available to the GPU tier.
- (C) 8188 clear, GPU idle, 14B present, but `decide()` still returns CPU → a **routing
  bug** (e.g. a stale "ComfyUI owns GPU" latch that doesn't clear, or the persisted
  chat pinned to a GPU-only tag that never re-resolves).

## Step 2 — fix the actual cause

- **If (B):** make the launcher able to ensure a **GPU** chat model, not only the CPU one.
  `START_LOCAL_AGENT_GUI.ps1` today ensures/pulls the CPU startup model on `:11435`;
  add an equivalent optional check for the GPU tier — ensure `EQUAL_SHARES_PRIMARY_REASONING_MODEL`
  is present on the GPU instance (`:11434`), pulling only from the launcher (never from a
  chat request), reporting a failed pull clearly, and never substituting a stock model.
  Confirm both Ollama instances share the same model store so a single pull is visible to
  both tiers; if they do, the fix is ensuring the server is up and the tag resolves, not a
  second copy.
- **If (C):** fix the routing logic so that once 8188 is clear and the GPU is idle,
  `decide()` re-polls the GPU catalogue and selects the 14B. Ensure any "skip GPU poll
  while ComfyUI owns the card" guard is **stateless per call** (re-evaluated every turn),
  not a latch that stays set after 8188 closes. Keep the existing protective behavior
  intact: while 8188 is listening OR VRAM is above the busy threshold, CPU is correct.
- **If (A):** no routing change — it's correct. Proceed to Step 3 only.

## Step 3 — make the reason visible (always do this)

The operator could not tell *why* it was on CPU. In the GUI status pill / `/api/status`,
show the concrete reason from `router`'s detail, e.g.:
`GPU busy — ComfyUI on :8188` / `GPU busy — 11.8 GB VRAM in use` / `GPU idle — using 14B`
/ `GPU server down`. This turns "mysteriously stuck on CPU" into a legible state. Do not
change the routing thresholds — only surface the existing reason.

## Constraints

- Never start/resume/monitor ComfyUI or a render; only *observe* port 8188 and VRAM.
- A render always wins; the protective CPU route while the GPU is owned must remain.
- `agent.answer()` stays transport-agnostic; `router` stays the single authority on GPU
  state; no new dependencies; server stays on 127.0.0.1.
- Do not weaken the abliterated-only chat allowlist or expose stock/vision models as chat.

## Verify (show commands/output)

- `python local_agent\router.py` before and after — the after-state, with 8188 confirmed
  clear and the GPU idle, must route to the 14B on the GPU host (or, if (A), clearly
  report why CPU is still correct).
- `python local_agent\test_router_switching.py` — still green (add a case for the
  fixed cause: e.g. 8188-clear + idle + 14B-present → GPU route; latch clears).
- `python local_agent\test_native_tool_calling.py` — still green.
- If the launcher changed: parse it with PowerShell's parser and confirm it still starts
  both servers.
- `validate_h3_prompt.py` still 124/124.

## Record it

Write `CHANGELOG/<today>_gpu_routing_fix.md` — the four diagnostic findings, the true
cause (A/B/C), exactly what changed, the before/after `router.py` output, and what stayed
unverified (anything needing a live render or a real GPU-idle window). Update
`local_agent/README.md` and the current handoff doc with the visibility change.
