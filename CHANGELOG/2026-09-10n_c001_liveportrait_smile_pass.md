# 2026-09-10n — C001_last non-diffusion smile repair passed

## Outcome

The locked C001_last wave now has a clearly visible smile without regenerating
the actor, room, clothing, body, or raised arm. The accepted candidate is still
pending operator approval, and production is deliberately paused before any
later still or video.

- Attempt: `72c3e47a11214b3dae1ee11f8821a99b`
- Policy: `c001-smile-liveportrait-v17/blind-contrastive-expression-gate-v5`
- Final still SHA-256:
  `b10512dafe45a610cfc10721bac71fbff5c5bb8a5f49c6b2043bfaa087a293df`
- Semantic gate: `reference-blind-continuity-face-crop-v10`
- Production status: `paused_for_identity_recovery`
- Approval status: `pending`

## Root causes and fixes

1. The RealVisXL/FaceDetailer series exposed a stable tradeoff: identity-safe
   settings retained the serious mouth; settings strong enough to create a
   smile changed identity. Mouth inpainting also produced opaque face plates.
2. The already-installed AdvancedLivePortrait `ExpressionEditor` was therefore
   added as a non-diffusion recovery mode. It geometrically retargets the
   detected face and composites it over the immutable wave.
3. The first LivePortrait attempt (`14304c86...`) produced a valid smiling
   image, but `image_render.py` incorrectly collected ExpressionEditor's
   temporary UI preview along with the `SaveImage` result. Evidence collection
   now accepts only explicit `SaveImage` node outputs.
4. The full-frame blind VLM pass repeatedly called the small full-body face
   neutral/serious even when the prompt-aware pass and human inspection saw a
   smile. The gate was strengthened, not bypassed: it now preserves a dedicated
   face crop and performs an additional prompt-free reference-versus-candidate
   expression comparison with literal smile cues.

## Evidence

The exact Qwen2.5-VL Caption V4 GGUF + matching projector reported:

- prompt-aware verdict: pass;
- same person, hair, facial hair, clothing, and room geometry: all true;
- candidate more smiling than the reference: true;
- same identity in the expression comparison: true;
- smile cues: `upturned mouth corners`, `visible teeth`;
- raised hand, full body, both feet, living room, and no camera/tripod: present.

A direct pixel comparison against immutable wave SHA
`9374d6e23a5d81e42dbea377c5b8a4203ea521f731ee6364bc2675853b13b014`
found that only 20,819 pixels (2.6473% of the frame) changed, confined to face
bounding box `[451, 80, 599, 228]` in the 1024x768 image.

## Installed assets used

No download was required. The isolated renderer used existing local assets:

- `comfyui-advancedliveportrait` / `ExpressionEditor`;
- five LivePortrait safetensors under the shared `liveportrait` model folder;
- `face_yolov8n.pt` under the shared `ultralytics` model folder.

No SDXL checkpoint, VAE, KSampler, IP-Adapter, ControlNet, or video model was
loaded for the successful expression edit.

## Verification

```powershell
python -m py_compile work/image_render.py work/run_prompt_pack_production.py work/test_still_retry_not_stop.py
python -m unittest local_agent.test_production_integrity local_agent.test_media_accuracy_gate work.test_still_retry_not_stop -q
```

Result: `Ran 68 tests ... OK`.

The controlled supervisor was run only as:

```powershell
python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0
```

It stopped at the successful C001 smile guard. Port 8188 was released and the
GPU returned to idle. No video began and `outputs/equal_shares/**` was untouched.

## Next operator decision

Review and approve or reject C001_start and the C001_last v17 still. Do not
resume the remaining still pack or any video until that decision is recorded.
