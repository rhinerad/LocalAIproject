# Fix: `render_story_image_batch` job 1 fails with a ComfyUI/port-8188 error, blocking the other 6

**For:** a Claude Code session working directly in `COMFYUI_STORY_HANDOFF_2026-08-09`, with real access to the Windows machine (process list, `netstat`, and the actual log files — I do not have that from where I'm working, see "What I could not check" below).
**Effort:** Opus 5.5 at `xhigh` (or Fable 5.1 at `high`/`xhigh`) — this needs root-causing from real log evidence, not a mechanical fix.

## The symptom, verbatim from the agent

> The batch render job has started, but one of the jobs failed due to a ComfyUI backend issue on port 8188. The failure is unverified as it could be a temporary issue with the backend. The remaining six jobs are pending and will not start until the failed job is resolved. The error message indicates that the ComfyUI backend is listening on port 8188, which suggests that the backend is running but might be experiencing an issue preventing it from processing the render request. Until the failed job is fixed, the render process cannot proceed, and the stills sheet is not ready for review.
> Source: `render_story_image_batch` tool result.

**Do not treat this paraphrase as the root cause.** It's the agent's own natural-language gloss on a tool result, not the raw error. The actual `render_story_image_batch` failure entry (`failures[0]`) carries a `log` path and a `status`/`error` field with the real text — read that first, from the actual chat/session where this happened, before doing anything else.

## What's already true by design — don't "fix" these

- `render_story_image_batch` (`local_agent/tools.py:2509`) defaults `stop_on_failure=True`. On the very first launch or await failure it stops the loop and marks every remaining job `pending` with `reason: "not_started_after_failure"` (see the `pending.extend(...)` blocks at both failure sites). **The 6-pending-jobs behavior is correct, intentional gating — the bug is entirely in why job 1 failed, not in the stop-on-failure logic.**
- Inside the per-job launch loop, if the launch error string contains `"owns the backend"` or `"already listening on port 8188"`, it already retries up to 60 times with `sleep(max(2.0, poll_s))` between attempts before giving up (lines ~2544-2560). So if job 1's failure really was the literal "already listening" preflight refusal, it already survived ~60 retries and still couldn't clear — that's meaningful evidence in itself (see hypothesis below), not something to patch by just raising the retry count further.

## The two places a "port 8188" failure can actually come from — trace which one it was

1. **Preflight refusal, before any process is spawned** — `work/image_render.py:preflight_execute()` (called from `local_agent/tools.py` around line 2085-2094):
   - `_live_owner()` — refuses if `work/runtime/image_render_owner.json` has a live PID (an "Equal Shares" render owns the GPU).
   - `_port_open()` — a raw `socket.connect_ex(("127.0.0.1", 8188))` check. Refuses with `"another ComfyUI backend is already listening on port 8188"` if **anything** is bound to that port — including a ComfyUI instance started by a completely different script.
   - I read `work/runtime/image_render_owner.json` directly: right now it's cleanly `{"pid": 0, "purpose": "released", "released_at": "2026-09-14T23:20:54Z"}` — 9 days old, not implicated. But check it again live when you actually run this — it may have changed since I looked.

2. **Backend actually launched but never became healthy** — `work/image_render.py:_start_owned_backend()`:
   - Spawns a **new, private** ComfyUI subprocess bound to `127.0.0.1:8188` (`args = [..., "--listen", "127.0.0.1", "--port", "8188", ...]`), writing stdout/stderr to `work/runtime/logs/comfy_<timestamp>.stdout.log` / `.stderr.log`.
   - Polls `{API}/object_info` for up to `startup_timeout=240` seconds. If the process exits early, or never answers in time, it raises `ImageRenderError(json.dumps(record))` where `record` has `state` (`process_exited` / `alive_not_listening` / `cleanup_failed` / etc.), `error`, and `elapsed_seconds` — **this JSON blob is the actual root-cause evidence**, and it's what should be sitting in the batch failure's `log`/`status` fields. Read the matching `comfy_*.stdout.log` / `.stderr.log` pair by timestamp for the real crash trace.

## My working hypothesis — check this first, it's cheap to confirm or rule out

`render_story_image` / `render_story_image_batch` and the full video pipeline (`generate_video.py`, called by both `batch_run_backrooms_gvd.py` and `master_batch_runner.py`) **all submit to the same `http://127.0.0.1:8188`**, but `render_story_image` additionally tries to launch and own its *own* private ComfyUI process on that exact port. Earlier today (confirmed directly from `progress.json`/`master_batch`) there were two genuinely long, real GPU renders on this machine: a ~23-minute MiniMax render via `batch_run_backrooms_gvd.py` finishing 17:54, and another ~21-minute one via `master_batch_runner.py` finishing 21:47. A ComfyUI server process doesn't necessarily exit just because the client script that submitted to it finishes — if either of those left its backend resident on port 8188, then when `render_story_image_batch` ran afterward, `_port_open()` would correctly see the port occupied and refuse to start its own instance, retry up to 60 times, and still find it occupied the whole time (because nothing is going to release a backend that a different, unrelated pipeline intentionally left running).

To check: on the real machine, look at what's actually listening on 8188 right now (`netstat -ano | findstr :8188`, then match the PID to a process) and compare its start time against the timestamps of those two earlier renders and against when the failed batch job ran. Also check whether `local_agent/tools.py`'s `stop_all_comfyui` tool (or its underlying `/interrupt` + `taskkill` logic, lines ~671-710) clears the block — if calling that resolves it, that's strong confirmation this was a leftover backend from one of the other two pipelines, not a genuine crash.

## What I could not check from here

I only have bridged filesystem/shell access to this machine via a Linux VM, not a real Windows shell — `netstat`, `powershell`, and live process inspection all silently no-op from where I'm working. I could read the *static* files (code, the owner JSON, timestamps in `progress.json`) but not live process/port state at the moment of failure, and I don't have the actual failed job's raw `log`/`status` payload — only the operator's paraphrase of it. You have real access; use it to get the actual evidence before fixing anything.

## Fix guidance, conditioned on what the evidence shows

- **If it's the leftover-backend collision (hypothesis above):** the underlying behavior (refuse rather than silently steal another pipeline's ComfyUI instance) is correct and shouldn't change — GPU/port collisions are exactly what this is guarding against. The real fix is operator-facing: `render_story_image_batch` should surface a clear, actionable message ("another ComfyUI backend is already running on port 8188 — likely left over from a full video-pipeline render; stop it or wait for it to finish before requesting stills") instead of the vague retry-then-fail-silently-into-"backend issue" behavior it has now. Consider whether it should also check `batch_render_queue_owner.json` / any known "this port is intentionally held by pipeline X" markers before retrying blind, so it can name the actual owner instead of just detecting an occupied socket.
- **If it's a genuine startup crash** (`state: process_exited` or similar in the `ImageRenderError` JSON, with a real traceback in `comfy_*.stderr.log`): fix the actual cause shown in that log (missing model path, bad launch arg, `--disable-all-custom-nodes` incompatibility, etc.) rather than papering over it with a longer timeout or more retries.
- **If `startup_timeout=240` was just too short** (e.g. `state: alive_not_listening` with `elapsed_seconds` close to 240 and no error, meaning it was still loading): raising the timeout is reasonable, but confirm first that it actually would have succeeded given more time — check whether the process was still alive and progressing (model loading in the stdout log) at the deadline, not just guessing.

## Verification before declaring this done

Don't stop at a passing unit test or a code read. Re-run the actual failed batch (or a small 2-3 job batch through `render_story_image_batch`) for real and confirm all jobs reach `completed`, not just job 1. If the leftover-backend hypothesis is confirmed, also verify the fix doesn't regress the legitimate case — two genuinely competing renders should still refuse/queue, just with a clear message instead of a confusing dead-end.
