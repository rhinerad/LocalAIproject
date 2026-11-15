# Fix: `_start_owned_backend`'s 240s startup deadline races a backend that actually finishes starting

**For:** a Claude Code session (Opus 5.5 at `xhigh`, or Fable 5.1 at `high`/`xhigh`) working in `COMFYUI_STORY_HANDOFF_2026-08-09/work/image_render.py`. Small, narrow fix, but it's inside GPU-launch code with thermal-safety checks that other sessions have been actively working around today — read `local_agent/router.py`'s `gpu_busy()` and the `thermal_guard` module before touching anything nearby, and don't change thermal-guard behavior as a side effect.

## The symptom, with real evidence (not a paraphrase)

Live run today: a `render_story_image` job for the Backrooms Sitcom Audition Scene Start Image 1 failed with:

```json
{"state": "alive_not_listening", "pid": 37960, "error": "startup deadline exceeded", "elapsed_seconds": 240.016, ...}
```

Job log: `work/runtime/agent_image_jobs/Scene-Start-Image-1_20260924_181712.log`.

**This is not a crash or a genuine hang.** I read the *actual* ComfyUI process log the job-status JSON only quotes the tail of — `work/runtime/image_render_runtime/logs/comfy_20260924_181714_618110.stderr.log` (full file, not just the `last_100_lines` snapshot the failure record captured). It shows completely normal startup: GPU detected (RTX 5080, 16303 MB VRAM), custom nodes correctly skipped (`face_detail=False` was passed, per the `--disable-all-custom-nodes` flag — confirming `2026-09-24u`'s fix worked and this is a genuinely different failure), then:

```
[INFO] Starting server

[INFO] To see the GUI go to: http://127.0.0.1:8188
[INFO] Global interrupt (no prompt_id specified)
```

**The backend actually finished starting and became ready.** The `Global interrupt` line immediately after is `image_render.py`'s own cleanup code tearing down a backend that had, in fact, just become healthy — it just crossed the finish line a few seconds after the code had already given up on it.

## Root cause — `work/image_render.py:1093-1163`, `_start_owned_backend`

```python
state = "alive_not_listening"
deadline = started + startup_timeout          # default startup_timeout=240
while time.monotonic() < deadline:
    if proc.poll() is not None:
        state = "process_exited"
        raise ImageRenderError("backend exited before readiness")
    thermal_guard.check_running_ceiling(print, "comfy-startup")
    try:
        _get_json(f"{API}/object_info", timeout=min(2, max(.1, deadline-time.monotonic())))
        proc.server_ready = True
        ...
        return proc
    except ImageRenderError:
        time.sleep(min(.5, max(0, deadline-time.monotonic())))
raise ImageRenderError("startup deadline exceeded")
```

The loop condition (`while time.monotonic() < deadline`) and the final `raise` are unconditional — there is no readiness check *at* the deadline, only checks strictly *before* it. If the backend becomes ready in roughly the same window the last poll attempt fails and the deadline ticks over, this code gives up on a backend that (per the real log) was about to succeed. On today's run the gap was small — the process log shows `Starting server` essentially right at the boundary.

## Fix

Do not change `thermal_guard.check_running_ceiling` or the polling cadence inside the loop — those are working as intended and other sessions rely on them for GPU safety. The fix is narrow: **one more readiness check immediately when the deadline is reached, before raising** — e.g., after the `while` loop exits, attempt `_get_json(f"{API}/object_info", timeout=...)` one final time (a couple of seconds is enough, this is not a retry loop, just closing the exact race observed) and return `proc` on success exactly as the loop body does, only raising `"startup deadline exceeded"` if that final check also fails.

Separately, consider whether `startup_timeout=240` deserves a modest bump (e.g. 270-300s) given how close today's real run ran to the wire — but treat that as a secondary tuning question, not a substitute for closing the race itself. A longer timeout narrows the window but doesn't eliminate a structurally-unconditional cutoff the same way a final check does.

## What NOT to conclude from this

- This is **not** the port-8188-contention failure documented in `fix-render-story-image-batch-8188.md` (no other process held the port; this backend's own launch attempt got to `Starting server`).
- This is **not** a recurrence of the `face_detail`/`realpro_flux` bug fixed in `2026-09-24u` — that error did not appear in this run at all, which is itself confirmation that fix is working.
- The owner lock was released cleanly (`work/runtime/image_render_owner.json` shows `"purpose": "released"`), so there's nothing stuck to clear before retrying.

## Testing

- Unit test: mock `_get_json` to fail for N calls then succeed exactly at/after the point `time.monotonic()` would exceed a fake deadline; assert the final check catches it and `_start_owned_backend` returns the process rather than raising. Also keep a negative-control test where the final check also fails, confirming `"startup deadline exceeded"` still raises correctly when the backend is genuinely never going to come up.
- Don't stop at the unit test. Re-run a real `render_story_image` call (the same Scene Start Image 1 job is a fine candidate) and confirm it now actually reaches a rendered PNG + manifest under `outputs/stories/`, not just a clean process start. Today's evidence is strong but is one sample; confirm the fix holds on a second real run too.

## Operator note

The two job logs from today's resubmission attempts used different `story` values between attempts (`Backrooms-Sitcom-Audition---Scene-Start-Image-1` vs. `Scene-Start-Image-1`) — worth checking which one the operator actually wants used consistently before the next resubmission, since `story` becomes part of the output directory path under `outputs/stories/`.

## Gotcha (recorded every time this bites)

An unscoped `grep -r` / `find` across `local_agent` without excluding `local_agent/vendor`, or an unscoped `find` across the whole `outputs/stories` tree, reliably times out or returns an unusable wall of results — that tree has hundreds of story directories. Scope every search explicitly (a specific filename pattern, `-maxdepth`, or a direct known path) rather than a bare recursive search.
