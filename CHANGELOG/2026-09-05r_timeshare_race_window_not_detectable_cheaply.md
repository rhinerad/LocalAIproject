# 2026-09-05r — Task #40: TOCTOU race window has no cheap live signal

## Scope

🔵 lane, Task #40. Investigation only, same standard as #39 — no code
shipped, verdict is "not viable without a poller."

## Finding

The ~29s (measured up to ~38s live, 2026-09-04 DynamicVRAM probe) lag is
not "VRAM is low" — it's that VRAM stays flat at the idle baseline (345
MiB) for tens of seconds after a real generate has already been enqueued
and is visible in `/queue`. The only thing that actually sees a racing
render at T0 is `/queue` or a live owner PID, not `nvidia-smi`. Every
cheap surface considered fails for the same reason: `status()` doesn't
carry a live `/queue` read on the 8188 path (`gpu_busy()` returns on TCP
before `nvidia-smi`), the GUI's 15s status poll doesn't refresh
`_TIMESHARE_QUEUE_CACHE`, and `farm_health` is the wrong plane entirely
(Celery, not ComfyUI). A badge countdown after `/free` would just label
the residual window unconditionally, not detect an actual racer. The only
honest live signal is sampling `/queue`/owner again on a timer — which is
a poller, explicitly out of scope (same as #39, and it would also violate
the 2026-09-04aa invariant that removed the interim WARNING bypass line).

## What already exists and is sufficient

The claim path already double-checks `/queue` before and after `/free`
inside `decide()` — if a prompt lands during the ~20s `clear_vram` RPC,
it fails closed to CPU. That's a one-shot check, not a live badge, and
it's already the correct mitigation for the window it can see.

## What was not done

No status line, no `farm_health` field, no restored WARNING log, no
poller. The residual race is left documented as an accepted risk
(remaining-unsafe items 1/2/11 from the original design), same as when it
was first accepted.

## Task #41 unblocked

Both gating tasks (#39, #40) are now resolved — negatively, but resolved.
Task #41 (audit GPU-timeshare behavior across every routed model) can
proceed.
