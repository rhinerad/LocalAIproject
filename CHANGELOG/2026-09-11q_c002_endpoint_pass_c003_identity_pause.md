# 2026-09-11q — C002 endpoint pass; C003 identity recovery pause

## C002 last-frame outcome

- The original C002-last whole-frame i2i attempts were preserved and rejected:
  they changed the actor identity and room geometry.
- A single hash-pinned reference-edited endpoint donor was staged at
  `work/runtime/identity_donors/c002_last/c002_last_endpoint_imagegen_v1.png`.
- Its SHA-256 is
  `2a8bbb960c0680076f983032e6bddf5be98c071265be7fc78a2874ed37ddd9b0`.
- The delivered C002-last still passed the mechanical gate and exact
  Qwen2.5-VL Caption V4 / llama.cpp semantic and continuity gates. It is in
  attempt `40536d95cea1489d9fe8915d4e9d88f5`.
- This acceptance advances still production only. It does not authorize video.

## Reliability repairs

- `work/run_prompt_pack_production.py` now retries one malformed VLM transport
  envelope against the same image before declaring semantic QA failed; a review
  formatting fault must not create a replacement render.
- Added a bounded `i2i_identity` mode to `work/image_render.py`. It runs the
  SDXL i2i sampler through the installed IP-Adapter Face model using a
  hash-recorded face crop, instead of relying on prompt text to retain identity.
- Successful direct hash-pinned endpoint attempts now write
  `identity_control.json`, closing a provenance receipt gap.

## C003 start stop condition

- C003-start's two unconditioned i2i attempts were rejected for face/hair/beard
  drift.
- The first full-frame IP-Adapter attempt preserved the actor but changed room
  details and did not sufficiently reset the performance.
- The second allowed IP-Adapter attempt also failed strict semantic QA (room,
  pose, and facial-hair evidence). The configured two-attempt policy has now
  paused production at C003-start. All renders, receipts, and QA files remain.
- No video generation began. The GPU was released after the stop.

## Verification

```
python -m py_compile work/image_render.py work/run_prompt_pack_production.py
$env:PYTHONPATH=(Join-Path (Get-Location) 'work')
python -m unittest test_still_retry_not_stop test_image_render local_agent.test_production_integrity local_agent.test_media_accuracy_gate -q
```

Result: 107 tests passed.

## Next decision

Do not restart C003 blindly. A new recovery policy needs a smaller, explicitly
bounded room-preserving pose edit or a separately reviewed, hash-pinned C003
reset donor.
