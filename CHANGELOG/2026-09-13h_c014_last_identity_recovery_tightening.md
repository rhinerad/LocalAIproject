# 2026-09-13h — C014 last recovery: QA wording and final identity lock

## Evidence from the first conditioned attempt

Attempt `2926d2f975c0441fad4f56d7790a1393` rendered and preserved a broadly
matching crouched actor, clothes, apartment, and camera-free frame. It did not
pass exact Qwen2.5-VL review: the blind continuity comparison still identified
face, hair, facial-hair, and room-detail drift. The artifact and all QA are
preserved as a failure.

The deterministic assertion layer separately flagged the canonical wording
"Fixed tripod-mounted camcorder viewpoint" as a positive request for a visible
tripod. That was a parser wording error: the same sentence explicitly says the
device is outside the image. It did not identify visible equipment in the
actual still, and Qwen's blind observation also reported no camera/tripod.

## Change

The second and final `c014-last-fullframe-ipadapter-v1` attempt now:

- lowers denoise from `0.48` to `0.36` after the first conditioned failure;
- raises FaceID/IP-Adapter weight from `0.95` to `1.08`;
- uses a narrowly derived, truthful QA description that says equipment is
outside the image without describing a tripod-mounted viewpoint;
- retains the same two-attempt recovery ceiling and exact-Qwen QA gate.

The canonical prompt remains bound in the receipt and is not modified.

## Verification

Ran the production syntax check and the bounded still/QA suites:

```powershell
python -m py_compile .\work\run_prompt_pack_production.py
python -m unittest work.test_still_retry_not_stop local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: **115 tests passed**. The updated regression confirms the first and
second recovery attempts use distinct, evidence-driven controls instead of a
seed-only repeat.

## Boundaries

No prior artifact was replaced. No video was started. The final C014 recovery
attempt still needs its normal mechanical and exact-model semantic review; it
is not pre-approved by this change.
