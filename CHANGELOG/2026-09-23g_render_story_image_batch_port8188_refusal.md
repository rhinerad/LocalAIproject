# 2026-09-23g — render_story_image_batch: port-8188 refusal now structured, named, and correctly retried

## Symptom
Chat `1d4a42d3b5834081`, 22:23:15: `render_story_image_batch` (7 jobs) failed job 0
and left 6 `not_started_after_failure`. The agent paraphrased it as a vague
"ComfyUI backend issue on port 8188".

## Evidence (live, not inferred)
- Raw failure (`local_agent/runtime/agentic_tasks/1d4a42d3b5834081.json`):
  `"error": "image-render preflight refused: a ComfyUI backend is listening on port 8188", "phase": "launch"`.
- No new `work/runtime/agent_image_jobs/*.log` since 2026-09-07 → nothing was spawned.
- `netstat`: 127.0.0.1:8188 LISTENING pid 52504, created 21:18:03, command line
  `ComfyUI\main.py --listen 127.0.0.1 --port 8188 ...` (Rockernow install),
  launched by `cmd.exe /c A:\Users\rhine\.grok\long-running-background-tasks\start_comfy_rockernow.bat`.
  Its log (`comfy_detached.log`) shows it served today's video prompts
  (13:11, 11:08; last prompt 22:00:51, globally interrupted 22:12). Queue idle at 22:4x.
- `work/runtime/image_render_owner.json`: released (pid 0, 2026-09-14) — not implicated.

## Root cause
1. `render_story_image` checks `router.gpu_busy()` first and re-raised its reason
   verbatim. That wording ("a ComfyUI backend is listening on port 8188") contains
   neither `"owns the backend"` nor `"already listening on port 8188"`, so the
   batch's 60-attempt retry loop broke on attempt 1 (zero retries), and the
   error never named who held the port.
2. Latent, same mechanism: `image_render.py` writes its manifest *before*
   `_stop_owned_backend()` in `finally`, so `await_story_image_job` reports job N
   complete while job N's own backend still holds 8188. Job N+1 then hit the same
   unmatched router wording and could fail with no retry.

The refusal itself was correct ("One backend, ever"); the bug was classification
and reporting.

## Change (`local_agent/tools.py`)
- New `Port8188BusyError(ToolError)` carrying `blocked_by`; every 8188 refusal in
  `render_story_image` (router path and `_port_open` path) raises it via
  `_port_8188_refusal()`. Message keeps the prefix
  `image-render preflight refused: another ComfyUI backend is already listening on port 8188`.
- `blocked_by.kind`:
  - `draining_image_job` — `image_render_owner.json` names a live pid (our prior still job).
  - `foreign_backend` — `_describe_port_8188_holder()`: listener pid (netstat),
    process + launcher (CIM ancestry, first non-`main.py` ancestor), start time,
    `/queue` running/pending, live `batch_render_queue_owner.json`, plus an
    operator-facing `summary`.
- `render_story_image_batch`: retries `draining_image_job` (and legacy
  "owns the backend") with the existing 60 × max(2, poll_s) budget; a
  `foreign_backend` gets `_FOREIGN_BACKEND_GRACE_ATTEMPTS = 3` then fails with
  `blocked_by` on the failure entry and a `next_step` naming the holder and
  forbidding "temporary backend issue" framing or stopping it without operator
  confirmation. Stop-on-failure / pending semantics unchanged.
- Backups: `local_agent/{tools.py,test_render_story_image.py,test_story_stills_batch_review.py}.bak_port8188_20260923T224853`.

## Tests
- Added: 2 in `test_render_story_image.py` (router wording → structured refusal;
  live image owner → draining, no holder probe), 3 in
  `test_story_stills_batch_review.py` (foreign fails fast with named holder, 6
  pending; draining retried to completion; end-to-end through the real
  `render_story_image` preflight). Existing port test now stubs the holder probe.
- `python -m unittest test_story_stills_batch_review test_render_story_image` → 36 OK.
- Regression test fails against the pre-change backup (`KeyError: 'blocked_by'`).
- Also OK: agent_timeshare_gpu_gate, capability_routing, gpu_vram_num_ctx,
  managed_prompt_pack, router_comfy_timeshare, router_status_busy,
  router_switching, story_image_reveal.
- `test_native_tool_calling`: 1 pre-existing failure
  (`test_execute_plan_second_step_still_runs_after_first_raises`), identical
  against the pre-change backup; unrelated.

## Live verification
- Real 2-job `render_story_image_batch` with pid 52504 resident: refused in 12.0 s,
  `blocked_by.kind=foreign_backend`, named pid 52504 + the Grok `.bat`, job 1
  `not_started_after_failure`, no job log / no spawn.

## Operator-approved recovery (same session)
- Queue was idle; `tools.stop_all_comfyui({})` → `stopped_pids: [52504]`
  (53028/51864 exited with it). Port 8188 no longer listening — confirms the
  block was the resident Grok-launched backend, cleared by the existing stop tool.
- After that, `router.gpu_busy()` still reports busy: "another compute process is
  on the GPU: ...Python312\python.exe" (301 MiB used). The only Python312
  processes are the local agent's `server.py` (35476) and `media_watcher.py`
  (9252). Restarting them was operator-approved but blocked by the session's
  permission classifier; left to the operator.

## Unverified
- Full success path (all jobs `completed`) NOT run: requires stopping pid 52504
  (another agent's resident backend) and GPU-gate approval — awaiting operator.
- The running local-agent server (pid 35476, started 22:12) still has the old
  `tools.py` loaded until restarted.
