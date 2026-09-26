# 2026-09-10l - Stage B finalize: controlled face_refine_identity C001_last smile test

## Preconditions

- `python work/test_still_retry_not_stop.py` → **19 tests OK**
- Port **8188 CLOSED** (no LISTEN owner) before and after
- GPU idle preflight: **31 C / 0% / ~277 MiB**; post: **33 C / 0% / ~265 MiB**
- Wave SHA-256 `9374d6e23a5d81e42dbea377c5b8a4203ea521f731ee6364bc2675853b13b014` (immutable)
- Identity/QA anchor (C001_start `baaf329e…`) SHA-256 `0b944e9ab752d1b1d97d6816ed0014dbbce7c950f1804dd7c980b4daa5de7003`

## Policy under test

- Version: `c001-smile-facedetailer-stageb-v12`
- Revision: `face-crop-stage-b-visible-smile-v1`
- Mode: `face_refine_identity` (Impact Pack FaceDetailer + SDXL IP-Adapter Face)
- IP-Adapter weight: `0.60`
- FaceDetailer denoise: `0.50`
- Prompt: visible natural friendly sitcom smile (slightly open allowed); no open-mouth ban
- `max_attempts: 1`; still-only; C001 locked; no video

## Single live attempt

Attempt `6d7c18754f324d468b125828ecc5be04`  
Supervisor log: `production_2026-09-10_smile_stageb_v12.log`  
Prompt id: `ea9e92a9-f1e6-4a1f-981b-190ff16237f0`

### Models / sampling

- Checkpoint: `RealVisXL_V5.0_fp16.safetensors` (profile `realvisxl`)
- IP-Adapter Face: `ip-adapter-plus-face_sdxl_vit-h.safetensors`  
  SHA-256 `677AD8860204F7D0BFBA12D29E6C31DED9BEEFDF3E4BBD102518357D31A292C1` (handoff-bound)
- Seed `277847775`, 1024×768, steps 35, cfg 6.0, `dpmpp_2m_sde` / `karras`
- Peak GPU during run ~**43 C / ~10.9 GB**; Comfy released after

### Graph nodes (face_refine_identity)

Primary classes observed in the submitted graph / render receipt:

- Checkpoint / CLIP / VAE loaders for RealVisXL
- CLIP Text Encode (positive/negative)
- LoadImage (wave working reference + identity face crop)
- IP-Adapter Face stack (IPAdapterModelLoader / CLIPVisionLoader / IPAdapterAdvanced, weight 0.60)
- UltralyticsDetectorProvider (bbox) → **FaceDetailer** (denoise 0.50, bbox_crop_factor 2.2, cycle 1)
- SaveImage → `stories/pack_…/renders/6d7c1875…`

Identity face crop SHA-256: `3b76f20848b25f5eece16b5a03c5c6ca2ebc3e6c40701cf8b47edba9894eaece`

### Output

- Still SHA-256: `75c5f53d1e4a447e048797633efc721b234bdb3f76e87a712c8a734613ee112b`
- Manual look: same living-room full-body framing, raised open hand, beard/clothes intact; mouth reads **neutral/serious**, not a clear smile; no camera/tripod; no grey mouth plate

### Exact Qwen2.5-VL gate (blind evidence)

- Continuity: `same_person`/`same_hair`/`same_facial_hair`/`same_clothing`/`same_room_geometry` = **true**
- Blind expression: **neutral**
- Raised hand: present (`right_hand_position: raised, palm up`)
- Full-body / both feet: true
- **Fail reason:** `blind evidence does not show the required smile or grin`
- Prompted verdict ignored when blind disagrees

### Result

**Rejected.** Ledger `paused_for_identity_recovery`. Do not promote. No video.  
Stage B FaceDetailer at IP 0.60 preserved identity/wave/hand but did not produce a blind-visible smile.
