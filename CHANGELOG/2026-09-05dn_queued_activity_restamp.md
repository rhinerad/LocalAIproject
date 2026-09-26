# 2026-09-05dn — Queued-media activity cards restamp from media_queue

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dn**.

Follow-up to `2026-09-05da` (queued card stayed `announced` after the
watcher finished) and `2026-09-05cn` (activity-trace v1). No Equal
Shares work. No watcher SSE push. No `trace_id`.

## What the watcher already does

`media_watcher.py` never talks to the chat GUI. On success it calls
`media_queue.complete(job_id, result)` which writes
`media_queue/done/{id}.json` (`done_at` + `result` string). Failures go
to `failed/{id}.json` (`error`). Cancelled jobs go to `cancelled/`.
`GET /api/media_queue` already lists those buckets for the sidebar pill,
but strips the result body and the GUI never used them to restamp chat
cards.

Desktop `see_image` always enqueues `{queued: true, job_id, reason}`
with **no filename**. The assistant message stores that `job_id` on the
`queued` activity card. The job JSON does not need a conversation id
for this path.

## Small/safe fix (prototyped)

Do **not** add a watcher → HTTP SSE back-channel (the turn's SSE stream
is already closed). Reconcile on read, poll on an open tab:

1. `media_queue.get(job_id)` — load one job from any state folder.
2. `GET /api/chat` runs `reconcile_conversation_activity` and **persists**
   restamped cards so a later reopen does not depend on queue files.
3. Announced `queued` cards with a terminal job become
   `state=result` (`done`) or `state=error` (`failed`/`cancelled`),
   `source=observation`, clipped summary, **no invented filename**.
   Pending/processing stay `announced`.
4. Open GUI: `refreshQueue` already polls `/api/media_queue`;
   `restampQueuedFromQueue` updates `.life[data-kind=queued][data-job]`
   stamps to Observed result/error. Extra 5s poll only while an
   announced queued card is on screen.

`APP_REVISION` / `$ExpectedAgentRevision`:
`2026-09-05-queued-activity-r80`.

## Tests

```
python -m unittest test_activity_trace test_launcher_revision -v
```

26/26 OK. New: pending stays announced; done restamps without filename;
failed/cancelled are observed errors; store round-trip + GET-shaped
reconcile.

## Live

Chat `c04571a9c1d84e70`, workspace `general`. 8B called `see_image` on
`local_agent/uploads/activity_trace_probe.png`. SSE `queued` job
`d430cfd6362f4e79`, no filename. First `GET /api/chat`:
`state=announced`.

The live `media_watcher.py` instance did **not** drain the job in ~90 s
(`qwen25_vl_runtime_available` was false; `ensure_qwen25_vl_runtime`
is the watcher's lazy start and did not bring a VLM up in this window).
Completion was written with `media_queue.complete` — the same function
the watcher calls after a successful `_run_vision_gpu`. That is the
durable signal this fix reads.

Second `GET /api/chat`:

```
kind=queued state=result source=observation
label=media job complete job_status=done
summary={"available": true, "analysis": "the square is red"}
```

No `filename`. `restore_activity` matches. Probe PNG removed.

A watcher-owned VLM finish would hit the same files and the same
restamp. Starting the caption VLM was not required to prove the
back-channel, and was not done here.

## Files

- `local_agent/media_queue.py`
- `local_agent/server.py`
- `local_agent/static/index.html`
- `local_agent/START_LOCAL_AGENT_GUI.ps1`
- `local_agent/test_activity_trace.py`
- `TODO.md`
