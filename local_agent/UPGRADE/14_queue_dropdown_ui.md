# Claude Code / Codex prompt — media-queue dropdown: status, timer, "waiting on", cancel

## Status — BUILT 2026-08-25

- `media_queue.py` now has cancellation evidence, cooperative cancellation
  flags, progress/timing fields, and render/VRAM/CPU/position wait reasons.
- `media_watcher.py` checks cancellation between safe analysis boundaries and
  converts the flagged job to `cancelled/` rather than deleting it.
- `server.py` exposes a local-only, media-id-only `POST /api/media_queue/cancel`.
- The desktop Queue pill opens a polling dropdown with per-job progress,
  client-ticking elapsed timers, reasons, and cancel buttons.
- Focused queue and endpoint-helper regression coverage is in
  `test_media_gpu_queue.py`. Live visual interaction is still operator-facing.

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/media_queue.py`,
`local_agent/media_watcher.py`, `local_agent/server.py`, and
`local_agent/static/index.html` first. This builds on the queue from UPGRADE 09
(already built). Stdlib only; server stays on `127.0.0.1`. **Do not touch the render
pipeline or `outputs/equal_shares/**`.**

## Goal

A dropdown in the GUI that shows the media queue live: every item, how far along it
is, how long it has been waiting, **what it is waiting on**, and a **cancel** button
that removes an item the operator no longer wants.

## What exists now (build on it, don't rewrite)

- `media_queue.py`: `enqueue` / `claim_next` / `complete` / `fail` / `recover_stale` /
  `list_queue`. Jobs have `id`, `kind`, `queued_at`, `args`; state is the directory
  (`pending/ processing/ done/ failed/`), written atomically.
- `server.py`: `GET /api/media_queue` → `mq.list_queue()`; a `queued` SSE event fires
  when `_vision` enqueues.
- The watcher polls, claims the oldest pending job, processes, and moves it to
  `done/`/`failed/`. It does not currently write progress.

## Job 1 — richer queue data (`media_queue.py` + the watcher)

- **Cancel support.** Add `cancel(job_id) -> str`:
  - pending → move the job file to a new `cancelled/` state dir (add `"cancelled"` to
    the states and to `list_queue`), stamped `cancelled_at`. Never hard-delete —
    evidence rule.
  - processing → write a cooperative **cancel flag** the watcher checks between items
    and between video frames; the watcher aborts the in-flight request, unloads if it
    loaded a model for that job, and moves it to `cancelled/`. (If UPGRADE 12's
    pre-emption abort exists, reuse that mechanism; otherwise add the between-step
    check here.)
  - done/failed/already-cancelled → no-op with a clear message.
- **Progress + timing fields.** When the watcher claims a job, stamp `started_at` and
  set `progress` (e.g. `{"stage": "loading model"}` → `{"stage": "analyzing",
  "done": 3, "total": 6}` for a 6-frame `analyze_video`, updated per frame). Single-
  shot image jobs can use stage strings (`queued → loading → analyzing → done`).
- **"Waiting on" reason** for each pending job — compute in `list_queue` (or a helper):
  - a render owns the card (`router.gpu_busy()` true via queue owner / port 8188) →
    `"waiting for the GPU — a render is using it"`;
  - GPU free but no model tier fits (`router.gpu_free_mb()` below the smallest need) →
    `"waiting for VRAM to free up"`;
  - otherwise → `"queued — N item(s) ahead"` (its position, honoring priority if
    UPGRADE 12's interactive/batch tag is present);
  - audio jobs waiting on CPU/Whisper → say that.
- **Enrich `list_queue()`** to return, per item: `id`, `kind`, a human `name` (the
  source filename from `args.path`), `status`, `queued_at`, `started_at`,
  `elapsed_seconds` (now − queued_at), `progress`, `waiting_reason`, and `priority`
  if present. Group by state. Keep it cheap — it is polled.

## Job 2 — endpoints (`server.py`)

- Extend `GET /api/media_queue` to return the enriched per-item data above (counts +
  the item lists for at least pending/processing, plus recent done/failed/cancelled).
- Add `POST /api/media_queue/cancel` with `{"id": "..."}` → calls `mq.cancel(id)` and
  returns the outcome. Reject unknown ids cleanly. It only ever cancels a media job;
  it never touches a render or `render_queue_owner.json`.

## Job 3 — the dropdown (`static/index.html`)

- A queue control near the existing GPU-status pill: a button showing the pending
  count (e.g. "Queue (3)") that opens a **dropdown** listing items, newest activity
  first, processing before pending.
- Each row shows: an icon for the media type, the file name, a **status** line
  (`processing 3/6` / `pending`), a **live timer** ("waiting 2m 14s" from
  `elapsed_seconds`, ticking client-side between polls), the **waiting-on** reason for
  pending items, and a **Cancel** button (✕) that calls the cancel endpoint and
  refreshes. Processing rows show progress (a small bar or `done/total`); a cancel on
  a processing row asks nothing fancy — it sets the flag and the row flips to
  "cancelling…".
- Poll `GET /api/media_queue` on the same cadence as the status pill (and refresh
  immediately on the `queued` SSE event and after a cancel). Show an empty-state
  ("nothing queued") rather than a blank menu.
- Keep the desktop layout unchanged otherwise; no dependency, plain JS/CSS matching
  the existing dark styling.

## Verify (show commands/output; stdlib, mockable)

1. `python local_agent/test_native_tool_calling.py` and any queue test still green;
   `validate_h3_prompt.py` still 124/124.
2. New stdlib tests for `media_queue`: `cancel` on a pending job moves it to
   `cancelled/` (not deleted); `cancel` on done/unknown is a clean no-op;
   `list_queue` reports `elapsed_seconds`, `progress`, and a correct `waiting_reason`
   for a pending job under mocked `router.gpu_busy`/`gpu_free_mb` (render-busy vs
   VRAM-short vs position-in-line).
3. Endpoint test: `POST /api/media_queue/cancel` with a real pending id cancels it;
   a bogus id returns a clean error (drive the handler or a factored function).
4. Manually: enqueue a couple of jobs (or use the media-queue live path), open the
   dropdown, confirm the timer ticks, the waiting-on text is right, progress advances
   on a processing job, and Cancel removes an item.

## Record it

Write `CHANGELOG/<today>_queue_dropdown_ui.md` (what/why/evidence/verified/
unverified), add its row to `CHANGELOG/README.md`, and note the dropdown + cancel
endpoint + new queue fields in `local_agent/README.md`. If UPGRADE 12 was not yet
built, note that this added its own between-step cancel check that 12 can later reuse.
