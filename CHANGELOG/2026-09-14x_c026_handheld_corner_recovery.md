# 2026-09-14x — C026 handheld-corner POV recovery

## Diagnosis

C026 start has two rejected normal SDXL attempts. Its authored still wording
simultaneously asks for a view through the actor's physical handheld camcorder
and a visible full actor. That geometry would require a forbidden selfie,
mirror, or external camera. The earlier non-semantic candidate is a close
portrait against a plain yellow wall; it is preserved but is not accepted
evidence for C026.

## Change

`work/run_prompt_pack_production.py` now has a C026-start-only recovery after
two completed base failures. It retains the accepted C025 corridor as the i2i
reference, uses a 0.68 bounded scene reframe, and specifies the actual
deliverable: a Level 0 right-angle corner and short continuation corridor from
the camera-holder's POV. Faces, torsos, full bodies, legs, shoes, visible
camera hardware, mirrors, and external views are hard-rejected by the delivery
QA prompt. The policy permits at most two attempts.

The generic runner recognizes `scene_i2i_reframe` as ordinary i2i rather than
incorrectly routing the scene into a face/pose inpaint workflow.

## Verification before render

```
python -m py_compile work/run_prompt_pack_production.py work/test_still_retry_not_stop.py local_agent/media_accuracy_gate.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 178 tests passed.

## QA parser correction

The first two v1 recovery renders are preserved. Exact Qwen V4 judged the
first corner candidate visually correct, but the mechanical prompt parser
mistook the prohibitive phrase "Do not depict ... visible camera body" for a
positive camera request and required an action pose despite an empty-scene
instruction. `media_accuracy_gate.py` now strips prohibitive clauses before
positive-camera detection and accepts equivalent face/torso prohibitions. The
C026 v2 policy adds the explicit sentence that no pose/action is requested and
is bounded to two attempts. The full suite now has 179 passing tests.

## Stop conditions

This does not start video work. Existing attempts and QA evidence are retained.
If both bounded C026 scene-reframe candidates fail exact Qwen2.5-VL Caption V4
QA, production pauses for reassessment rather than seed-spinning.
