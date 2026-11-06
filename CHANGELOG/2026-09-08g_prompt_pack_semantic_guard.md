# 2026-09-08g — Prompt-pack semantic/continuity guard

## Root cause

The prior production attempt generated independent text-to-image frames with no
reference handoff, reused the same two seeds for the entire pack, and did not
explicitly forbid visible camera equipment. Mechanical checks therefore marked
visually incorrect camera/actor compositions as usable. No videos were produced
because the still phase stopped at C014.

## Changes

- Added explicit visible-camera, lens, tripod, operator, selfie, and reflection
  negatives to every exported still job.
- Added sequential previous-last-frame reference metadata and i2i staging for
  subsequent start frames; references are checksum-verified before staging.
- Preserved attempt-specific receipts and rejected historical-PNG fallback.
- Kept semantic QA and approval separate from mechanical file checks; no still is
  auto-approved for video.
- Startup diagnostics now retain process/command/log evidence and use a writable
  project-local Numba cache.

## Verification

`python -m py_compile work/image_render.py work/run_prompt_pack_production.py local_agent/prompt_pack_production.py local_agent/media_accuracy_gate.py`

`python -m unittest local_agent.test_managed_prompt_pack local_agent.test_media_accuracy_gate -q` — 11 passed.

`python -m unittest discover -s local_agent -p 'test*production*.py' -q` — 21 passed.

Bounded ComfyUI startup probes reached `/object_info` in 9.0–11.3 seconds with
the isolated runtime. The 102-clip production task remains stopped at 26/204
stills, semantic review pending, and 0/102 videos; no full rerun was started.
