# 2026-09-24y — image_render: final readiness probe at the startup deadline; default 240 s → 300 s

## Problem

`work/image_render.py` `_start_owned_backend` polled `/object_info` only while
`time.monotonic() < deadline`, then raised `"startup deadline exceeded"`
unconditionally. The last in-loop probe's timeout is clamped to the time left
(down to 0.1 s), so a backend that starts listening in that final window is
torn down.

Evidence: `work/runtime/agent_image_jobs/Scene-Start-Image-1_20260924_181712.log`
failed `alive_not_listening`, `elapsed_seconds: 240.016`. The health snapshot
taken at the deadline ends at `No OpenGL_accelerate`; the full stderr
(`work/runtime/image_render_runtime/logs/comfy_20260924_181714_618110.stderr.log`,
last written 18:21:16 local vs. deadline 18:21:14.6) then shows `Starting server`,
`To see the GUI go to: http://127.0.0.1:8188`, and `Global interrupt` — the last
being `_stop_owned_backend`'s own `/interrupt` reaching a now-listening server.
The backend became ready ~0.5–1.5 s **after** the deadline, not at it.

Startup history (413 `server_ready` health records in that logs dir): median
51 s, but 225.8 s, 228.2 s and 239.1 s had already come within seconds of 240;
verification run 2 below took 185.2 s. So the budget, not only the race, was
too tight.

## Change

- After the loop exits: if the process has exited → `process_exited` as before;
  otherwise one `thermal_guard.check_running_ceiling` (same order as the loop)
  and exactly one `/object_info` probe with a full 2 s timeout. Success returns
  the process with a `server_ready` health record carrying
  `ready_on_final_check: true`; failure raises `"startup deadline exceeded"`
  unchanged. Not a retry loop.
- `startup_timeout` default 240 → 300. `verify_prompt_pack_startup.py` still
  passes its own `--seconds`.
- In-loop cadence and thermal-guard behaviour unchanged. `router.gpu_busy()`
  unaffected (owner file + port 8188 already mark the GPU busy during startup).

## Tests

`local_agent/test_production_integrity.py::IntegrityTests::test_startup_final_check_at_deadline`
(fake monotonic clock): ready exactly at the deadline → returns proc, health
`server_ready` + `ready_on_final_check`; never ready → still raises
`startup deadline exceeded`, stops the backend, health `alive_not_listening`.
Against the pre-fix code the ready case fails with the production error.
Full file: 55 tests OK (includes 2026-09-24w's history-poll tests).

## Real-run verification (story `startup-deadline-fix-verify`, realpro_flux, no face_detail)

- Run 1 (seed 1): startup 10.5 s, PNG + manifest
  `outputs/stories/startup-deadline-fix-verify/manifests/image_42221665-4145-4e60-a434-c57d80f0d987.json`.
- Run 2 (seed 2): startup 185.2 s, then failed on the separate `/history`
  timeout fixed in 2026-09-24w; its orphan PNG `bfa0d801…_00001_.png` was later
  adopted by another session (2026-09-24z).
- After 2026-09-24w landed (GPU gate re-checked idle before each run):
  seed 3 startup 112.5 s → manifest `image_b3e278c9-cc00-4d3f-868b-d4c88e089930.json`;
  seed 4 startup 106.9 s → manifest `image_ef520c10-3359-4e4f-863f-fb2420e8c61c.json`.
  Both exit 0, owner released, zero `history poll failed` lines in either log.
- No real run exercised the final-probe branch (every startup was under the
  deadline) or the 2026-09-24w retry branch (no /history timeout recurred);
  both branches are covered by unit tests only. This change does not alter the
  render graph, so no golden-reference workflow diff applies.

**Cleanup (operator-requested, 2026-09-24):** all verification outputs were
deleted — `outputs/stories/startup-deadline-fix-verify/` (4 manifests, including
the one adopted in 2026-09-24z) and
`outputs/stories/_comfy_output/stories/startup-deadline-fix-verify/` (4 PNGs).
The job logs under `work/runtime/agent_image_jobs/startup-deadline-fix-verify_*`
and the backend logs/health records were kept as evidence.

## Operator notes

- The two Scene Start Image 1 resubmissions used different `story` values
  (`Backrooms-Sitcom-Audition---Scene-Start-Image-1` vs `Scene-Start-Image-1`);
  pick one before resubmitting. The original prompt is not recoverable from the
  chat log (tool args are stored only as a sha256).
- In chat `local_agent/chats/149209bf6e4b42ce.json` the agent told the operator
  Scene Start Image 1 "has been successfully generated" although the batch
  reported `failure_count: 1`. No such image exists.
