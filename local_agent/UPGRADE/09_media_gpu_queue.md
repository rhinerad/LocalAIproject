# Claude Code prompt — tiered vision load, "GPU Busy" queue, and a GPU watcher

> **Source preserved from Google Drive (2026-08-24):**
> [`09_media_gpu_queue.md`](https://docs.google.com/document/d/1Z3Wdu3Xcj1AAUdEjSQPepQsy7WKvZKbJ5GoC59KmzQU/edit?usp=drivesdk).

Paste into Claude Code, run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Self-contained. Read `local_agent/README.md`
and `CLAUDE.md` first — they are binding. Internet **is** available now, so
`ollama pull` is allowed. Do not touch the render pipeline or `outputs/equal_shares/**`.

## The behaviour to build

When the operator asks the agent to look at an image/video or listen to audio, the
sensory model must load on the **GPU**, but the GPU is often occupied by a render.
The required policy, in order:

1. **Primary model, full GPU load.** If the GPU has enough free VRAM to hold the
   primary abliterated Qwen vision model *fully*, load it there and process now.
2. **Smaller model, full GPU load.** If the primary will not fully fit, try a
   smaller vision model that needs less VRAM. If *it* fully fits, use it now.
3. **Queue + "GPU Busy".** If even the smaller model will not fully fit, do **not**
   run it half-offloaded to CPU. Emit **`GPU Busy`** to the GUI and enqueue the
   file(s) in a persistent watch queue, telling the operator it will be processed
   when the GPU frees.
4. **Watcher drains the queue.** A background watcher polls the GPU; the moment
   enough VRAM is free to fully load a model (and no render owns the card), it
   loads the best-fitting model and processes the queued items in order, writing
   results back so the GUI shows them. Then it idles until more work or more VRAM.

This is a deliberate change from today's behaviour in `media_tools._vision`, which
falls back to the **CPU** Ollama server when the GPU is busy. A Qwen-VL model on
four CPU threads is unusably slow, so **remove the CPU fallback for vision** and
replace it with the tiered-GPU + queue policy above. (Whisper transcription stays
CPU-side as it is — see "Audio" below.)

## What "fully fits" means — detect it deterministically

Ollama will silently offload layers to system RAM when a model does not fit,
producing a slow "partial" load. Detect fit **before** loading, by free VRAM:

1. Add `router.gpu_free_mb() -> int | None` next to `router.gpu_memory()`, reading
   `nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits` (same
   subprocess/except pattern; `None` when nvidia-smi is unavailable).
2. Define per-tier VRAM requirements (weights + KV headroom), as named constants,
   e.g. in `capabilities.py`:
   - primary `qwen3-vl-abliterated:8b-q8_0` → ~11500 MB
   - smaller `qwen3-vl-abliterated:4b`      → ~7000 MB
   Add a safety margin constant (e.g. `VRAM_SAFETY_MB = 1024`) on top.
   Tune the numbers with a comment citing the model file sizes (8B Q8_0 = 8.71 GB
   + f16 mmproj 1.16 GB; 4B ≈ 6.1 GB).
3. A tier "fully fits" iff `gpu_free_mb() is not None and free >= need + margin`
   **and** `router.gpu_busy()` reports no render owning the card (queue owner /
   port 8188 / foreign compute process). **Fail safe:** if `gpu_free_mb()` is
   `None` (nvidia-smi missing), treat as *does not fit* → queue. An unknown GPU is
   never permission to load.

## The smaller model

Add the smaller tier to `capabilities.VISION_PREFERENCES` (created in the
2026-08-22 vision-watcher change) so selection stays deterministic. Pull it (net is
allowed):

    ollama pull huihui_ai/qwen3-vl-abliterated:4b

or import a local 4B GGUF if the operator prefers. Give `capabilities.py` a way to
report, per tier, `(model_name, vram_need_mb)` so both `media_tools` and the
watcher choose the same tiers from one source of truth — e.g.
`capabilities.vision_tiers() -> list[dict]` returning the installed, vision-capable
tiers largest-first with their VRAM needs.

## The queue (persistent, stdlib, atomic)

- Store under `local_agent/media_queue/` — `pending/`, `processing/`, `done/`,
  `failed/` subdirs, one JSON job file per item. No database, no deps.
- A job records: `id`, `created` (pass a timestamp in; do not rely on wall-clock
  inside any workflow), `media_type` (`image`|`video`|`audio`), `path`(s),
  `question`, `crop`/frame args, `status`, and on completion `model`, `tier`,
  `result`, or `error`.
- Writes must be atomic (write temp, `os.replace`) so a crash never leaves a
  half-written job. Move the file between dirs to change state.
- A single module `local_agent/media_queue.py` owns enqueue / claim-next / complete
  / fail / list, transport-agnostic (no HTTP knowledge), so the server, the tools,
  and the watcher all use it.

## Where the tiering plugs in

- `media_tools._vision(...)`: replace the CPU-fallback block. Compute the best
  tier that fully fits (via `capabilities.vision_tiers()` + `router.gpu_free_mb()`).
  If one fits, load that model on the GPU and return the analysis as today. If none
  fits, **enqueue** the item(s) and return a structured
  `{"queued": true, "reason": "GPU Busy", "queue_id": ...,
    "position": N}` result — the tool result the model/GUI shows.
- `see_image` / `analyze_video`: unchanged entry points; they still call `_vision`,
  which now either analyses or queues. `analyze_video` already extracts frames
  first — enqueue the extracted frame paths so the watcher needs no ffmpeg re-run.
- **Audio** (`transcribe`): Whisper runs on CPU, so it does not need GPU VRAM. But
  the operator wants audio queued too when the machine is busy. Enqueue audio jobs
  with `media_type:"audio"`; the watcher processes them through the existing CPU
  Whisper path, gated on "no render active and the CPU chat model can be evicted"
  rather than on VRAM. Keep the existing one-CPU-model-at-a-time eviction.

## The watcher

`local_agent/media_watcher.py`, mirroring the project's watchdog conventions:

- Single-instance (own owner/lock file under `local_agent/media_queue/`), bound to
  nothing (no network server); pure local loop. `--once` does one drain pass and
  exits (for tests/cron); default loops every ~15 s.
- Each pass: if `pending/` is empty, idle. Else pick the largest tier that fully
  fits right now (`gpu_free_mb` + not `gpu_busy`); if none fits and there are only
  vision jobs, stay idle and log "waiting for GPU". For each processable job:
  claim → move to `processing/` → run the same code path as the live tool →
  move to `done/` with the result (or `failed/` with the error). Never delete a
  source file.
- It loads the model once and processes as many queued items as fit that window,
  then optionally `router.unload(GPU_HOST, model)` when the queue drains so it does
  not hold VRAM against the next render. Respect the one-owner rule: never load
  while `gpu_busy()` says a render owns the card.
- Start it from `START_LOCAL_AGENT_GUI.ps1` alongside the server (or document a
  separate launch). Log to `local_agent/media_queue/watcher.log`.

## GUI (`server.py` + `static/index.html`)

- New SSE event kind `queued` emitted when `_vision` queues: data
  `{count, reason:"GPU Busy", position}`. In `index.html`'s EventSource switch
  (alongside `route`/`tool`/`note`/`error`/`done`), render a clear inline
  card: **"GPU Busy — N item(s) queued; the agent will watch them once the GPU is
  free."**
- Add `GET /api/media_queue` returning `{pending, processing, done, failed}` counts
  and recent completed results. Add a small queue indicator in the GUI (near the
  existing GPU-status pill that already shows "GPU busy — render has it") that shows
  the pending count and lets the operator see a completed result when the watcher
  finishes. Poll it on the same cadence as the status pill.
- When the watcher completes an item, its result must be retrievable in the GUI via
  `/api/media_queue` (surfacing it into the originating conversation is a bonus, not
  required).

## Constraints (do not violate)

- Standard library only (PIL is already a dep; no new pip deps beyond the Ollama
  model pull). Server stays on `127.0.0.1`.
- `router.gpu_busy()` semantics and the "unknown GPU = busy / does-not-fit"
  fail-safe rule are preserved everywhere.
- One GPU owner ever. The watcher must never load a model while a render owns the
  card. Never delete a raw generation, reference, source media, or evidence.
- `media_queue.py` and `media_watcher.py` stay transport-agnostic; only `server.py`
  knows HTTP.

## Verify before claiming done (show commands + output)

Stdlib, mockable — no live GPU needed for these:

1. `python local_agent/test_native_tool_calling.py` and
   `python local_agent/test_media_analysis.py` → still green.
2. New tests (same mocking style as `test_media_analysis.py`):
   - patch `router.gpu_free_mb` high → `_vision` picks the **primary** tier;
     mid → picks the **smaller** tier; low (and `None`) → **queues** with
     `reason:"GPU Busy"` and never calls the CPU host.
   - queue round-trip: enqueue → `media_watcher --once` with `gpu_free_mb` patched
     high drains it to `done/` with a result; patched low leaves it in `pending/`.
   - atomicity: a job that raises during processing lands in `failed/`, never lost.
   - `GET /api/media_queue` returns correct counts (drive the handler with a fake
     request or factor the body into a testable function).
3. State plainly which items you ran live vs mocked.

Live checks to hand back to the operator (need the real GPU/Ollama — say they are
unverified): start a render to occupy VRAM, ask the agent to see an image, confirm
the GUI shows **GPU Busy** and the item queues; stop the render and confirm the
watcher loads the model and produces the analysis; confirm the primary loads fully
when the card is idle and the 4B is chosen when only partial VRAM is free.

## Record it (mandatory)

Write `CHANGELOG/<today>_media_gpu_queue.md` in the same session — the five
required answers (what/why/evidence/verified-after/still-unverified), with the test
output pasted. Add its row to `CHANGELOG/README.md`, mark this prompt built in
`local_agent/UPGRADE/00_INDEX.md`, and add the new files
(`media_queue.py`, `media_watcher.py`, tests) to `local_agent/README.md`.
