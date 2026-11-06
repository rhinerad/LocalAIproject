# 2026-09-05da — Activity-trace v1 live cards: failed-tool, permission-wait, queued-media

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05da**.

Follow-up to `CHANGELOG/2026-09-05cn_activity_trace_v1.md`, which shipped the
cards and unit-tested them but did not hit these three on a live turn.
No Equal Shares work. GPU gateway restored to `allow`; leftover pending
GPU request denied; leftover vision job `701ad9e469174126` cancelled.

Desktop `server.py` was already r79 (`2026-09-05-activity-trace-v1-r79`).

## 1. Failed-tool — matches unit tests

Chat `aff6ebfe72f64d37` (workspace `general`). Action-resolver
`list_dir` of a missing folder
`local_agent/this_dir_does_not_exist_activity_trace_v1`.

SSE: `conversation`, `tool`, `tool_result`, `done`.

`tool_result` body:

```
ERROR: …\this_dir_does_not_exist_activity_trace_v1 is not a directory
```

Persisted / restored DOM:

```html
<details class="act life" data-kind="tool_call" data-state="announced" data-source="proposal">
  <summary>Proposal — not proof of execution  tool_call list_dir</summary>
</details>
<details class="act life" data-kind="tool_result" data-state="error" data-source="observation">
  <summary>Observed error  tool_result list_dir</summary>
  <pre>ERROR: … is not a directory</pre>
</details>
```

The failed card is `kind=tool_result`, `state=error`, `source=observation`,
stamp **Observed error**, not Announced. Same contract as
`test_tool_result_error_is_observation_not_a_plan`.

## 2. GPU permission-wait — matches unit tests; sidebar is source of truth

Set `/api/gpu_gateway/mode` to `ask`, `/api/yield_gpu` (evicted 8B+14B),
then a new general chat `11c41e49a8774575`: “Reply with the single word
pong. Do not call any tool.”

SSE included:

```
note  GPU permission is pending in the sidebar: chat reasoning model load
route tier=cpu model=huihui_ai/qwen3-abliterated:8b
token/done  pong
```

Persisted activity began with

```html
<details class="act life" data-kind="waiting_for_permission" data-state="announced" data-source="observation">
  <summary>Announced — not yet observed  waiting_for_permission
  GPU permission is pending in the sidebar: chat reasoning model load</summary>
</details>
```

`GET /api/gpu_gateway` at the same moment: `mode=ask`, `pending_count=1`,
id `gpu_2885d6d687de`, workload `chat reasoning model load`,
key `chat:11c41e49a8774575:huihui_ai/qwen3-abliterated:14b`.

The turn was **not** blocked: it continued on the CPU 8B fallback and
answered `pong`. That matches the design note (sidebar is consent;
CPU fallback may already proceed) and
`test_gpu_permission_note_is_waiting_for_permission` /
`test_gpu_gate_block_is_not_a_blocked_turn`.

Stamp wording: because `state=announced`, the GUI uses “Announced — not
yet observed” rather than a dedicated “pending approval” phrase. The
kind is still `waiting_for_permission`. File-edit was not used; GPU
ask-mode is the path that emits the `note` the classifier knows.

After capture: mode restored to `allow`, pending request denied.

## 3. Queued-media — enqueue card is honest; complete-update is a real gap

New general chat `018792416a6a4baa`. 14B called `see_image` on
`local_agent/uploads/activity_trace_probe.png` (8×8 red PNG).
`see_image` always returns `{queued: true, …}` and does not invent a
filename.

SSE (abridged):

```
tool  see_image  path=…/activity_trace_probe.png
queued  {"queued": true, "reason": "queued for the next safe media GPU window",
         "job_id": "701ad9e469174126", "free_mb": 4116,
         "message": "Vision analysis queued. The background watcher will run it when the GPU is free."}
tool_result  (same JSON)
done  "The vision analysis has been queued… I cannot yet describe the color of the square."
```

Persisted `queued` card: `kind=queued`, `state=announced`,
`source=observation`, label = the reason, `job_id=701ad9e469174126`.
No `filename` key on the queued payload or the activity card.
`media_artifacts` stayed `[]`. The model did not claim a file existed.

The matching `tool_result` is `state=result` (the JSON is a queue
receipt, not `ERROR:`). That is consistent with the unit mapper, which
only marks `ERROR:` / `REFUSED` as error. The **queued** card is the
“not done yet” signal.

**Did not complete.** Job `701ad9e469174126` remained `pending` for ~90 s
with 14B resident, then another ~120 s after `/api/yield_gpu` (VRAM
~73 MB). `media_watcher.py` (PID 40012) never moved it to
processing/done/failed. Chat `activity` after that wait was unchanged
(`queued` still `announced`; no new media card). There is no SSE
back-channel from the watcher into a finished turn, so even a later
watcher completion would not restamp this card.

Cancelled the pending job after capture so it would not surprise-load
the VLM later.

This is a **real gap vs the “updates correctly once the job completes”
ask**, not vs the unit tests (those only map the enqueue SSE). Closing
it needs watcher → chat/GUI follow-up, not more enqueue styling.

## Files

Evidence only. No product code change in this pass.

- `CHANGELOG/2026-09-05da_activity_trace_live_cards.md`
