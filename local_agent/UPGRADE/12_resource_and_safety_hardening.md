# Claude Code / Codex prompt — resource + safety hardening (five items)

> **Source preserved from Google Drive (2026-08-24):**
> [`12_resource_and_safety_hardening.md`](https://docs.google.com/document/d/1sgMlp75p1Y6OysP3laKDXaX5OexP1HS5O1uLAItEhGU/edit?usp=drivesdk).

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/README.md`, `CLAUDE.md`,
`local_agent/router.py`, `local_agent/ollama_client.py`, `local_agent/media_watcher.py`,
`local_agent/media_queue.py`, and `local_agent/tools.py` first. **Do not touch the
render pipeline or `outputs/equal_shares/**`.** Stdlib only — no FastAPI, Pydantic,
Chroma, or any new dependency. Each job below is independent; land and CHANGELOG
each one. Verify with the existing suites plus the new tests noted; keep
`validate_h3_prompt.py` at **124/124** throughout.

## Job 1 — explicit `keep_alive` so models release VRAM promptly

**Built 2026-08-25.** Interactive chat retains its selected model for five
minutes; non-interactive Ollama planning and vision calls explicitly use zero
retention. Regression coverage verifies the API payload.

Today `keep_alive` is only used inside `router.unload()` (`:0`); every normal chat
and vision request uses Ollama's default **5-minute** retention, so a model can sit
in VRAM and delay a render launch.

- Add a `keep_alive` parameter through `ollama_client.chat` / `chat_stream` into the
  `/api/chat` and `/api/generate` payloads (default: unset = Ollama default).
- **Non-interactive callers pass a short window** or `0`: the media watcher
  (`_vision` path), the batch/queue processing, and standalone Whisper. Interactive
  desktop chat keeps a **modest** window (e.g. `"5m"` or `"2m"`) so the operator
  does not eat a reload on every message — do not set interactive chat to `0`.
- Where a queued job finishes and nothing else is pending, the watcher still
  explicitly `router.unload()`s (existing behaviour) — belt and suspenders.

Test (mock the HTTP post): a watcher/queue request carries the short `keep_alive`;
an interactive chat request carries the modest one; the value reaches the payload.

## Job 2 — quantized KV cache to reclaim VRAM at 32K

**Harness built; live measurement blocked on the exact 14B model.** See
`measure_ollama_kv_cache.py` and UPGRADE 18. Do not enable this setting until a
baseline and candidate report are recorded.

A 32K KV cache on an 8B–14B model is ~2–4 GB. Ollama can shrink it with
flash-attention + a quantized K/V cache — a **server-level** setting, not per
request.

- In `START_LOCAL_AGENT_GUI.ps1` (and any other place the GPU Ollama server is
  launched), set before `ollama serve`: `OLLAMA_FLASH_ATTENTION=1` and
  `OLLAMA_KV_CACHE_TYPE=q8_0`. Do this only for the **GPU** server; leave the CPU
  server default.
- **Measure, do not assume.** With it on, load the 14B at its 20480 context, read
  `nvidia-smi`, and record the VRAM delta vs off in the CHANGELOG. If q8_0 hurts
  answer quality noticeably, note it and fall back to f16 cache (still with flash
  attention). Confirm a render can still launch alongside the resident model.
- Document the tradeoff in `local_agent/README.md`: quantized KV saves VRAM, needs
  flash attention, and slightly lowers cache precision.

(No unit test — this is config + a measured VRAM figure. The measurement IS the
evidence.)

## Job 3 — mid-job render pre-emption in the media watcher

**Built 2026-08-25.** `MediaPreempted` is checked between video analysis frames
and action-extraction batches. The watcher requeues the same job with a
timestamped pre-emption record rather than failing it, then releases its VLM.

`media_watcher.py` checks `router.gpu_busy()` **before** loading a model but cannot
stop once a vision pass is running. Add cooperative pre-emption:

- Between queued items — and between frames within an `analyze_video` job — re-check
  `router.gpu_busy()`. If a render has claimed the card (queue owner / port 8188),
  **abort the in-flight Ollama request**, `router.unload()` the vision model, and
  **requeue the current job as pending** (do not mark it failed — it was pre-empted,
  not broken). Log a clear "pre-empted by render" line.
- The abort must be cooperative and clean: stop consuming the stream / close the
  request; never kill the render. One GPU owner ever; the render always wins.
- Guard against thrash: after a pre-emption, the watcher waits for the GPU to be
  free again (its normal poll) before reloading.

Test (mock `gpu_busy` to flip to True mid-drain): the current job returns to
`pending/`, the model is unloaded, and no partial result is written to `done/`.

## Job 4 — `propose_file_diff` tool (review before write)

**Built 2026-08-25.** The native tool returns a unified diff without writing;
it has the same protected-file refusal as `write_file`. Conversation rules now
require preview-before-apply.

For coding tasks the agent can call `write_file` directly. Add a safer default:

- New tool `propose_file_diff` in `tools.py`: given a path and proposed new content,
  return a **unified diff** (`difflib.unified_diff`) against the current file
  **without writing anything**. Same path guards as `write_file` (protected files
  refused; no traversal).
- Update `CONVERSATION_RULES`/tool guidance: for a file edit, **propose the diff
  first**; `write_file` applies it only after the operator sees it. Mirrors the
  project's existing "propose, don't auto-run" stance for builds/renders.

Test: `propose_file_diff` returns a correct unified diff and leaves the file
unchanged on disk; a protected path is refused; the schema is registered.

## Job 5 — interactive vs batch priority in the media queue

**Built 2026-08-25.** Queue records carry `interactive` or `batch` priority.
Direct desktop media requests are interactive; the watcher uses stable FIFO
within a tier and drains interactive jobs before batch work.

`media_queue.py` drains in arrival order. Add a priority tier so a live phone
photo/voice note is not stuck behind background frame extraction:

- Add a `priority` field to each job: `"interactive"` or `"batch"` (default
  `"batch"`). Phone-originated / live captures and direct operator `see_image` /
  `analyze_video` calls enqueue as `"interactive"`; bulk/background work as
  `"batch"`.
- The watcher's claim-next picks the **oldest `interactive` job first**, then oldest
  `batch`. Keep it stable (FIFO within a tier) — no starvation logic needed yet, but
  note in the code that a future change may age batch jobs up.

Test: with mixed jobs queued, claim order is all interactive (oldest→newest) then
batch; the field persists across the atomic move between queue dirs.

## Record it

One `CHANGELOG/<today>_resource_safety_hardening.md` covering all five (or one entry
per job if you prefer), each answering what/why/evidence/verified/unverified — with
the Job 2 VRAM measurement pasted. Add the row(s) to `CHANGELOG/README.md` and note
the new tool + queue field + KV setting in `local_agent/README.md`.

## Not in scope (deliberately deferred)

For the record, so a later session does not think these were missed: hybrid
dense+sparse retrieval and status/recency metadata filtering ride on UPGRADE 02 +
05 (the swappable scorer already exists for it); resumable/cursor streams and the
identity permission matrix are the Reticulum/Sideband track (permissions already
built in Sideband Phase 1); an auto project-state summarizer is intentionally NOT
added here because it would conflict with the evidence-based, in-session CHANGELOG
rule — `PROJECT_STATE.json` already covers machine-readable state.
