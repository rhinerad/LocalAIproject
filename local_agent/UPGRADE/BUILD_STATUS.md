# Local agent — build status board


> **Superseded for live state (2026-08-25).** The canonical current-state doc is
> `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md`, maintained by the Codex build
> sessions. Much has been built since this board (agentic loop 16, feedback/video
> actions 17, Qwen2.5-VL-NSFW-Caption V4 vision, RealVisXL smoke, storyboard
> approval gate, Sideband Tier A live). Read the canonical handoff first; this board
> is a Claude-side prompt-authoring snapshot only.

_Consolidated 2026-08-24. Source of truth for what is built vs pending across the
numbered UPGRADE prompts. Update the status column when a prompt lands._

## Upgrade prompts

| # | Prompt | Status |
|---|---|---|
| 01 | native tool calling | **BUILT** (2026-08-19) |
| 02 | context + retrieval | num_ctx half done (adaptive pair); **retrieval half PENDING** (refreshed prompt) |
| 03 | memory + polish | **BUILT** (2026-08-22) |
| 04 | sensory scaffolding | **BUILT** |
| 05 | models after internet | in progress (vision pin + reasoning pair models pulled) |
| 06 / 06a / 06b | remote access / USB / PWA | specs; superseded for the phone by the Sideband path (11) |
| 07 | batch renderer | **BUILT** (2026-08-22) |
| 08 | GUI ctx ceiling + Yield GPU | **PENDING** (refreshed to coordinate with adaptive pair) |
| 09 | media GPU queue + watcher | **BUILT** (2026-08-23) |
| 10 | dynamic 14B/8B fallback | **BUILT** (as `adaptive_huihui_reasoning_pair`) |
| 11 | Android via Sideband (LXMF) | Phase 0/1 + WiFi transport **BUILT** (2026-08-23); Tier B (fork) pending; live phone round-trip pending |
| 11-alt | native Android from scratch | reference alternative only |
| 12 | resource + safety hardening | **PENDING** (keep_alive, KV quant, pre-emption, diff tool, queue priority) |
| 13 | image + storyboard generator | **PENDING** (project core goal) |
| 14 | queue dropdown UI | **PENDING** |
| 15 | VRAM arbitration (anti-deadlock) | **PENDING** |
| 16 | agentic reasoning/execution loop | **BUILT through stage 5** (2026-08-24) |
| 17 | feedback + exemplar + video actions | **BUILT foundation** (2026-08-24) |
| 18 | attention runtime optimization | **RESEARCHED** (2026-08-24; SageAttention rejected) |
| 19 | vision model swap → Qwen2.5-VL NSFW | **PENDING** |

## Operator-only live verification (needs the real GPU / phone — cannot be done headless)

1. GPU-idle → GPU-tier routing check (`MORNING_CHECK.md`): close ComfyUI, `python local_agent\router.py`.
2. Activate the abliterated vision watcher: `ollama create` the vision Modelfile, confirm `ollama show` lists `vision`.
3. Media GPU queue (09) live: during a real render, queue a vision job, confirm GPU-Busy + watcher drain.
4. Dynamic 14B/8B (10) live: confirm >16K-token switch to 8B and OOM failover on the card.
5. Sideband (11): pair the phone's LXMF address on a shared Reticulum interface; stock-Sideband round trip.

## Open design threads (parked)
- **Coding assistant (coder model + sandbox)** — **BUILT 2026-08-25.**
  Coding mode is a picker choice for `EQUAL_SHARES_CODING_MODEL` (default
  `huihui_ai/qwen2.5-coder-abliterate:14b`) and swaps in a test-driven system
  prompt. `run_code` executes only under `local_agent/sandbox/run_<id>/`
  (timeout/output caps, network-off default, CPU only, phone default-denied).
  GPU-idle routing uses the 14B coder; a render still wins and coding falls
  back to CPU (slow — the GUI says so). Honest ceiling: strong local junior/mid
  coder, not frontier. A live coding session with the 14B-coder loaded is still
  unverified. See `CHANGELOG/2026-08-25_coding_mode_and_sandbox.md`.
- **Deep research + pluggable search backend** — **BUILT 2026-08-25.**
  `SearchBackend` + DuckDuckGo default; Brave/Serper/Tavily/xAI are stubs.
  Switching the search API is now a config change: set
  `EQUAL_SHARES_SEARCH_BACKEND` and `EQUAL_SHARES_SEARCH_API_KEY`, then fill in
  the ~20-line stub class. `deep_research` is a whitelist tool (bounded rounds/
  sources, cited JSON). One live GPU-idle run succeeded (python.org, 58.5 s,
  3 sources). Keyed APIs remain stubs. See
  `CHANGELOG/2026-08-25_deep_research_tool.md`.

- **Distributed compute / offload** — offload the chat LLM (and Whisper) to a 64 GB
  box to free the 5080 entirely. Judged worth doing for text; vision stays local unless
  the second box has a GPU. See `docs/design_notes/distributed_compute_assessment.md`.
  Prompt not yet written (paused by operator).

## Invariants that hold across everything (never weaken)

- A real render always wins: render owner / ComfyUI port 8188 → media waits.
- HTTP server stays on `127.0.0.1`; Reticulum/LXMF is the only remote transport.
- `tools.py` stays a fixed whitelist; remote (phone) identities default-deny state-changing tools.
- Never delete a raw generation, reference, manifest, audit record, source media, or queued job.
- Every change writes an evidence-based `CHANGELOG/` entry in the same session.
