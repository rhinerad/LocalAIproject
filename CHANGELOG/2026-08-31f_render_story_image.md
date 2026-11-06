# 2026-08-31 — built the missing general-story image renderer (`render_story_image`)

## The gap this closes

`2026-08-31e` fixed the *symptom* (the model claiming an image existed after
only calling `plan_story_image`) but left the *cause* on `TODO.md` as an
explicit unfixed item: "there is no tool anywhere in this agent that executes
a general-story image plan into an actual file." Every "make me an image"
request could only ever be planned, never produced.

## What was actually missing, and what wasn't

Reading `work/image_render.py` in full (it had never been read end-to-end in
this project before) showed the guarded execution path — GPU-ownership,
port-8188 exclusivity, thermal preflight, an owned throwaway ComfyUI backend,
prompt submission, output polling, and cleanup — **already exists** in that
script's `--execute --allow-model-load` CLI path (`preflight_execute()`,
`_write_owner()`, `_start_owned_backend()`, `_post_prompt()`,
`_wait_for_outputs()`, `_stop_owned_backend()`, `_release_owner()`). It was
never a stub. The actual gap was narrower than it looked from `tools.py`
alone: **no tool in the local agent invoked that CLI path**, and that CLI's
own preflight has no concept of this agent's `router.gpu_busy()` /
`gpu_gate` desktop-approval discipline that every other GPU action here goes
through — so a tool wrapping it couldn't just shell out to `--execute`
directly without adding that gate first.

## What changed

**`local_agent/tools.py`:**

1. **`render_story_image(args)`** — new tool. Before spawning anything, it
   runs the same checks `start_batch_render` runs: `router.gpu_busy()`,
   `image_render._live_owner()` (an Equal Shares render), `image_render.
   _port_open()` (someone else's ComfyUI), and a check of
   `image_render.IMAGE_OWNER` for a live PID from a previous image job — then
   the same `gpu_gate.request(...)` desktop-approval gate (or the phone
   paired-identity path via `__remote_render_identity`, mirroring
   `start_batch_render`). Only after all of that does it launch
   `work/image_render.py --story ... --execute --allow-model-load` as a
   **background** `subprocess.Popen` (the owned backend can take up to ~3
   minutes to start plus render time — too long to block a chat turn) and
   returns `{"started": true, "pid", "story", "log", "manifest_glob"}`
   immediately, with an explicit note that this is not completion.
   Same argument validation and bounds as `plan_story_image` (steps 1-60, cfg
   1.0-20.0, seed positive 64-bit, width/height multiples of 8 ≥256, i2i
   requires `reference_name`), and the same hardcoded `RealVisXL_V5.0_fp16.
   safetensors` model — the model is not caller-selectable, matching
   `plan_story_image`.
2. **`story_image_job_status(args)`** — new read-only tool. Reports
   `pid_running` (via the existing `_pid_is_live` helper), whether a
   `manifests/image_*.json` file exists under `outputs/stories/<story>/` and
   its parsed contents, and a bounded tail of the job's log file. Derives one
   of four states (`complete`, `running`, `finished_or_crashed`, `unknown`)
   deterministically rather than leaving the model to guess. Explicitly notes
   that the real output files live under `outputs/stories/_comfy_output/...`
   (the owned backend's private shared output root — **not**
   `outputs/stories/<story>/` itself), because that exact wrong-path
   guessing was part of the original reported failure ("the image is not in
   the output folder").
3. Rewrote `plan_story_image`'s `next_step` text: it no longer claims no
   execution tool exists (that's no longer true) — it now tells the model to
   call `render_story_image` next.
4. Registered both new tools in `TOOLS` and `_SCHEMAS`. `render_story_image`
   is a GPU-owning launch and is **not** added to `CONCURRENCY_SAFE_TOOLS`
   (same reasoning as `start_batch_render`). `story_image_job_status` is
   pure read-only (pid check + file reads) and **is** added to it.

**`local_agent/agent.py`:**

The `plan_only_pending` hallucination-correction state (added in `2026-08-31e`
for the plan-only case) is extended rather than replaced. It now also
activates when `render_story_image` returns `"started": true` (job launched,
not finished) or `story_image_job_status` returns any state other than
`"complete"` — the exact same premature-completion hallucination is just as
possible at this new, later stage ("the image has been generated" after a
background job was merely *queued*, or while `story_image_job_status` still
says `running`). The corrective reply now branches on *why* nothing is
confirmed yet (`plan_only` → call `render_story_image`; `render_pending` →
call `story_image_job_status` and wait for `state="complete"`), so the
operator gets an accurate next step instead of a generic denial. A genuine
`state: "complete"` result is deliberately left untouched — negative-control
tested.

## Why this is layered as background-job + explicit status tool, not a single blocking call

The owned ComfyUI backend startup alone can take up to 180 seconds
(`_start_owned_backend`'s own timeout), and `_wait_for_outputs` allows up to
900 more. A tool call that blocked the chat turn for up to ~18 minutes would
make the whole agent unresponsive and likely exceed any reasonable per-hop
timeout. Matching the existing `start_batch_render` pattern (propose → launch
in background → pid/log returned → caller polls) keeps this consistent with
how every other long-running GPU action in this codebase already works,
rather than inventing a new shape for this one tool.

## What was verified

- `python3 -m py_compile agent.py tools.py test_render_story_image.py
  test_native_tool_calling.py` — clean.
- New `test_render_story_image.py`, 15 tests, all mocking
  `subprocess.Popen`/`router.gpu_busy`/`gpu_gate.request`/a fake
  `image_render` module — no GPU or ComfyUI touched by the suite:
  refuses when GPU busy, when Equal Shares owns the GPU, when port 8188 is
  already listening, when another image job already owns the backend lock,
  and when the gateway is in Block mode; a granted request launches a real
  background process with `--execute --allow-model-load` in its argv and
  returns immediately without blocking; i2i without `reference_name` is
  rejected; both tools are registered with schemas;
  `render_story_image` is confirmed absent from `CONCURRENCY_SAFE_TOOLS` and
  `story_image_job_status` confirmed present; `story_image_job_status`
  correctly reports `finished_or_crashed` / `running` / `complete` against a
  temp directory tree, and includes a log tail when given a log path.
- 4 new tests added to `test_native_tool_calling.py` reproducing the
  render-pending hallucination and its negative control, using the same
  `agent.answer()` reproduction technique as `2026-08-31e`.
- Full regression sweep (with the documented `set_chat_busy` sandbox
  workaround): `test_native_tool_calling` 43/43, `test_render_story_image`
  15/15, `test_story_image_plan` 5/5, `test_router_switching` 41/41,
  `test_subtask_dispatch` 8/8, `test_retrieval_relevance` 4/4,
  `test_deep_research` 6/6, `test_run_code` 14/14, `test_agentic_state`
  11/11 — 147 tests total, 0 failures, 0 errors.

## What was NOT changed, and why

`work/image_render.py`'s own execution logic (`_start_owned_backend`,
`_post_prompt`, `_wait_for_outputs`, owner-lock handling) was not touched.
It already implements the correct safety discipline and is exercised
end-to-end by launching it as a subprocess exactly as designed — rewriting
it in Python inside `tools.py` instead of shelling out to it would duplicate
logic that already exists, already works, and already has its own operator
history, for no benefit.

## What is still unverified

Not yet run against a real ComfyUI backend or the real GPU. The mocked test
suite verifies the gating, argument validation, launch shape, and status
reporting logic; it does not verify that `image_render.py --execute` itself
still behaves as documented on the real workstation (that script's own
behavior was last touched and is documented independently — this change
only adds a caller in front of it). Real end-to-end verification requires
the operator to actually request an image on the real machine and confirm a
file appears where `story_image_job_status` says it will.

## Follow-up self-audit, same day: found and closed a concurrent-caller race

Auditing the code just written above (not new code elsewhere) found a real
gap before it ever shipped independently: `render_story_image`'s "no other
image render owns the backend" check and the actual subprocess launch were
two separate, unguarded steps. The desktop and a paired phone can call this
tool at nearly the same instant — `server.py`'s `ThreadingHTTPServer` already
serves both concurrently — so two threads could both pass that check before
either subprocess had written `image_render.py`'s own owner file, and both
would go on to fight over port 8188. That is exactly the "one backend, ever"
invariant `CLAUDE.md` treats as non-negotiable.

**Fix:** added `_IMAGE_RENDER_LAUNCH_LOCK` (`threading.Lock`) around the
entire preflight-check-through-launch sequence, plus a bounded (~5s) wait
after `Popen` for the subprocess to write its own real owner-file claim
before the lock is released — so a second caller blocked on the lock sees a
genuine live claim, not an empty file. The wait is deliberately short and
non-fatal on timeout: `image_render.py`'s own thermal wait (which runs
before it writes its owner file) can legitimately take longer than 5s on a
hot GPU, and that is not a failure, just an accepted residual race window —
the same tolerance this codebase already has for the pre-existing Equal
Shares `batch_owner` check elsewhere in `tools.py`. This closes the race
between two callers inside this one running agent process; it does not add
protection against a genuinely separate OS process invoking
`image_render.py` directly, which was never protected against either.

**Verified:** added
`test_concurrent_calls_are_serialized_and_second_sees_first_owner_claim`,
which runs two `render_story_image` calls on separate threads against a
fake `Popen` that synchronously claims a shared temp owner file, and asserts
deterministically (via the lock, not timing) that exactly one call succeeds
and the other is refused with "another image render owns the backend" — 16
tests in `test_render_story_image.py` now pass, and the full sweep across
`test_native_tool_calling` (43), `test_render_story_image` (16),
`test_story_image_plan` (5), `test_router_switching` (41),
`test_subtask_dispatch` (8), `test_retrieval_relevance` (4),
`test_deep_research` (6), `test_run_code` (14), `test_agentic_state` (11) —
148 tests total, 0 failures, 0 errors.

## Second follow-up self-audit, same day: phone identities could call this by default

Continued auditing the same new code and found a second real gap, more
serious than the first: `render_story_image` was never added to
`remote_security.GATED_REMOTE_TOOLS`. That frozenset is the explicit
allowlist requiring a per-identity operator grant before a paired phone can
call a sensitive tool — `start_batch_render`, `start_current_chat_render`,
`stop_all_comfyui`, `run_code`, and every other GPU/model-loading or
destructive action are all in it. `ToolContext.permits()` default-**allows**
anything not in that set. Because `render_story_image` was missing from it,
**any already-paired phone identity could launch a real GPU render with no
explicit grant at all** — directly contradicting `CLAUDE.md`'s "Phone
identities remain default-deny for this action. One ComfyUI, ever." This was
a real, live gap, not a hypothetical: `tools.call()` checks `context.permits(
name)` before the tool body ever runs, so nothing inside `render_story_image`
itself could have caught it.

A related but lower-severity bug sat next to it: `tools.call()` only injects
the trusted `__remote_render_identity` value for `start_batch_render` and
`start_current_chat_render`. Even after fixing the gate above, a *properly
granted* phone call to `render_story_image` would still arrive with
`__remote_render_identity` empty, so its own remote-identity branch would
never fire — it would instead fall into the desktop-only `gpu_gate.request(
"...", source="desktop tool", ...)` path, which expects a human at the
sidebar, not a phone.

**Fix:**
1. Added `"render_story_image"` to `remote_security.GATED_REMOTE_TOOLS`.
2. Added `"render_story_image"` to the trusted-injection set in
   `tools.call()` alongside the two existing render tools, so a granted
   phone call now correctly receives `__remote_render_identity` and takes
   the paired-identity branch instead of the desktop-gateway one.
3. Updated the tool's own registration text to state the phone-grant
   requirement, matching `start_batch_render`'s wording.

`story_image_job_status` was checked and left ungated — it is read-only (pid
liveness, manifest read, log tail), the same class of action as
`list_phone_schedules`/`capabilities`, which are also ungated.

**Verified:** two new tests — `tools.call("render_story_image", ..., context=
<unpaired phone>)` returns `"...not permitted..."` without ever reaching the
tool body, and `tools.call("render_story_image", ..., context=<phone with the
render_story_image grant>)` succeeds, calls `gpu_gate.snapshot()`, and never
calls `gpu_gate.request()` (proving it took the paired-identity branch, not
the desktop-sidebar one). Full sweep re-run including the LXMF/Sideband
remote-permission suites: `test_native_tool_calling` (43),
`test_render_story_image` (18), `test_story_image_plan` (5),
`test_router_switching` (41), `test_subtask_dispatch` (8),
`test_retrieval_relevance` (4), `test_deep_research` (6), `test_run_code`
(14), `test_agentic_state` (11), `test_lxmf_bridge`, `test_sideband_tier_b`,
`test_phone_scheduler`, `test_sonic_pi` — 200 tests total, 0 failures, 0
errors.
