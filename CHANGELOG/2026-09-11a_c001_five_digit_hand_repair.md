# 2026-09-11a — C001 five-digit hand repair and unambiguous blind QA

## Outcome

`C001_last` now has a physical, hash-bound candidate that passes the complete
still-image gate. The production supervisor stopped at the C001-only success
guard. No later still and no video was started.

Accepted automated-QA candidate (operator approval is still pending):

- attempt: `6e12ff2ab0b84085b765b7dd07a6bd4c`
- policy: `c001-hand-donor-composite-v28/five-digit-schema-v12-recheck-v1`
- still SHA-256:
  `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`
- exact VLM: `qwen25-vl-nsfw-caption:v4-q4_k_m`, llama.cpp
- VLM weights SHA-256:
  `e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d`
- projector SHA-256:
  `470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1`
- blind hand evidence: four upright fingers, thumb visible, five total digits,
  no extra/missing/fused digits, plausible wrist and anatomy, high confidence
- continuity evidence: same person, hair, facial hair, clothing, and room
  geometry

The candidate differs from the operator-rejected v17 source in 10,839 pixels
(1.3783% of the image), bounded to `[639, 44, 750, 180]`. The accepted source
face, body, clothing, room, lower arm, and frame were not regenerated.

## Root-cause sequence and preserved failures

Every failed attempt remains in its original evidence directory.

- v20 loaded the official hand detector after fixing nested Comfy model-path
  lookup, but produced four visible digits.
- v21 reconstructed both detected hands and created a second palm.
- v22 correctly selected only the topmost hand but generated a claw.
- v23 used MeshGraphormer plus the official SD1.5 hand-refiner ControlNet. It
  removed the claw but reconstructed the source's folded/sideways pose.
- v24 added a 21-joint open-palm map but strength 1.0 rendered the map as a
  skeletal hand.
- v25 reduced guidance and restored skin, but showed four digits.
- v26 separated the thumb chain and regressed to a two-finger gesture.
- v27 used the successful image edit only as a bounded, feathered pixel donor.
  Its pixels were visually correct, but the v11 VLM schema asked for a generic
  `finger_count_visible`; the VLM reported four fingers and excluded the thumb.
- v28 rechecked the identical pixels under schema v12, which separately records
  `upright_fingers_visible`, `thumb_visible`, and `total_digits_visible` and
  derives the total mechanically.

This was a QA schema correction, not a weakened anatomy threshold. Missing,
extra, fused, malformed, low-confidence, or non-five-digit hands still fail.

## Code and model-path changes

- `work/image_render.py`
  - supports bounded hand-detail, MeshGraphormer SD1.5 hand refinement, and
    SDXL explicit-hand OpenPose control;
  - validates nested Comfy model paths correctly;
  - records pose strength and end percentage.
- `work/run_prompt_pack_production.py`
  - records v20-v28 as bounded one-attempt policy revisions;
  - creates immutable hand masks and 21-joint pose maps;
  - can use a hash-pinned full-frame edit only as a bounded pixel donor;
  - pauses after any successful C001 smile/hand repair before continuing.
- `work/runtime/image_render_model_paths.yaml`
  - registers Impact Pack bbox/segm catalogues and the installed hand-refiner
    ControlNet path.
- `work/runtime/identity_donors/C001_open_palm_gpt_image_2026-09-11.png`
  - immutable donor, SHA-256
    `b28c86787b455f8c1507974b2073fe43cf98cac1cff1aa2f53a91c6f7cd9469c`;
  - the full donor is not an accepted frame and never crosses the bounded
    composite mask.

The built-in image editor created that donor from the rejected v17 frame with
this exact prompt:

```text
Use case: precise-object-edit
Asset type: final 4:3 image-to-video anchor still
Primary request: Repair only the malformed raised hand. Replace it with one photorealistic, anatomically correct adult male right hand making a relaxed friendly wave: open palm facing the viewer, exactly five clearly separated digits, four natural upright fingers and one distinct lateral thumb, natural nails, knuckles, palm creases, and wrist connection.
Input images: Image 1 is the edit target and immutable visual anchor.
Constraints: Change only the raised hand from the wrist upward. Keep every other pixel and detail unchanged: exact same fictional man's face and smile, hair, beard, body, olive overshirt, gray T-shirt, jeans, shoes, raised forearm and sleeve cuff, lowered arm, apartment living room, furniture, lighting, 4:3 framing, camera perspective, color, texture, and grain. Do not add any object to the hand. No visible camera, camcorder, tripod, or operator.
Avoid: extra fingers, missing fingers, fused fingers, skeletal hand, claw hand, two-finger gesture, peace sign, fist, object in hand, deformed palm, twisted wrist, extra hand, extra arm, changed face, changed pose, changed background, text, watermark.
```

Installed supporting files (not production outputs):

- `hand_yolov8s.pt`, SHA-256
  `70b540063fbc385736d8258970744a4afbc4cbf7932134bae3b24cdadeadec06`
- `control_sd15_inpaint_depth_hand_fp16.safetensors`, SHA-256
  `944b74b8ed3701117ffe5550026bbff2c8616f1c92b1bb2fee00e5349ff46256`
- `graphormer_hand_state_dict.bin`, SHA-256
  `b78081d105dc730c179eb0e2366bea999ceb4363070bb3aa1ae31fcf878a8a41`
- `hrnetv2_w64_imagenet_pretrained.pth`, SHA-256
  `41ed675bcd1f4f4b62a49bad64901f08f8b67ed744b715da87738f926daea685c`

## Verification

```powershell
python -m unittest work.test_image_render local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
```

Result: `Ran 90 tests ... OK`.

Live state after the successful check:

- phase: `stills`
- status: `paused_for_identity_recovery`
- supervisor PID: `null`
- port 8188: free
- GPU: 36 C, 0% utilization, 296 MiB baseline
- `C001_start`: QA pass, operator approval pending
- `C001_last`: QA pass, operator approval pending
- video phase: not started

## Next operator decision

Review `C001_start` and the v28 `C001_last` still. Explicit approval is required
before the pack can continue. Do not start video generation.
