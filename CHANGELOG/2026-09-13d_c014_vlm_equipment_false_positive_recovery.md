# 2026-09-13d — C014 start VLM equipment false-positive recovery

## Evidence

The C014 v1 managed reference copy had byte-identical actor and room continuity
with its accepted C013 anchor.  Its independent blind inspection explicitly
reported `camera_or_tripod_visible: false`, but the structured review inferred
visible production equipment from the contradictory phrase “Actor grips the
camera” in a prompt that otherwise forbade showing a camera.

## Change

The bounded C014 reference-copy recovery is now v2.  It retains the canonical
source prompt hash, but records a derived delivery/generation prompt replacing
that contradictory phrase with an actor bracing both hands on an **unseen**
support below the frame.  This matches the no-visible-camera requirement and
the actual accepted anchor.  The same hash-recorded image and ordinary exact
VLM QA gate remain in use.

## Verification

`work/run_prompt_pack_production.py` compiled and the 114 targeted production
tests passed.  Existing v1 evidence remains untouched.  No GPU task or video
job started during this code/test change.
