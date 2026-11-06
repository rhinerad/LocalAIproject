# 2026-09-13c — C014 start-frame continuity-anchor recovery

## Evidence

Both bounded C014-start RealVisXL i2i attempts were retained and rejected by
the exact Qwen2.5-VL Caption V4 gate.  The first drifted from the actor; the
second also failed the strict structured-review contract.  Their common,
already accepted C013-last reference is the immediately adjacent crouched-pull
setup.

## Change

The still runner now has one hash-recorded `c014_start_reference_copy` recovery
after those two base failures.  It copies only the immutable managed C013-last
anchor into a new C014-start attempt, writes independent source/output hashes,
and still submits the frame to the ordinary exact VLM QA gate.  It does not
start a GPU backend.  This is a continuity recovery, not an approval; the
output stays pending operator review.

## Verification

The production runner compiled and all 114 targeted regression tests passed.
No earlier attempt, source image, or QA receipt was overwritten.  No video
pipeline was enabled.
