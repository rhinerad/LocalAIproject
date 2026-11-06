# 2026-09-11h — C002 v5a bgnoise-prefill → SD erase (+ v5b)

## Context
C002_start policies v1–v4b all failed. Latest v4b attempt
`8bb167e1135c48ff8ffe2efdb9e16df4` (hang-corridor-on-erase-plate-v1).
Root cause unchanged: SDXL inpaint of the raised-hand hole tends toward
teal/green blobs. Classical non-SD erase dry-runs under
`work/_debug_c002_inspect/` (Telea, NS, hpull, seamless, multipass, etc.)
all fail visually (streak/blur). Best next seed: background-ring noise
prefill (outside pixels stay byte-exact), then SD `inpaint_identity`.

Dry-run plate already existed:
`work/_debug_c002_inspect/nonsd_bgnoise_prefill_dryrun.png` (grey slab — SD seed, not final).

## Code
- `work/run_prompt_pack_production.py`
  - new `write_bgnoise_prefill_plate(...)` (cv2): polygon mask → dilate →
    zero protected face → ring-sample fill → Gaussian blur inside mask only →
    assert outside-mask exact equality → write PNG
  - `apply_c002_identity_recovery`: detect `v4b_failed` /
    `v5a_failed`; check **before** existing `v4a_failed` branch
    - **v5a** (`c002-raised-hand-erase-v5a` / `bgnoise-prefill-sd-erase-v1`):
      fuller erase polygon (dry-run poly), prefill →
      `work/_c002_repair/v5a_bgnoise_prefill.png` as reference,
      denoise 0.50, `grow_mask_by` 0, `inpaint_identity`, no OpenPose
    - **v5b** (`c002-hanging-arm-openpose-v5b` / `hang-corridor-on-v5a-plate-v1`):
      mirrors v4b on newest v5a still
- `work/test_still_retry_not_stop.py`: v4b→v5a, v5a→v5b, outside-mask exact tests

### Hashes
- `work/run_prompt_pack_production.py` SHA-256:
  `3f9674c5523ea89c39bcb58d5b546b06d97dd7b821fa0b23a78e3e2815021fdb`
- `work/test_still_retry_not_stop.py` SHA-256:
  `5a1d289a560e430d413976ce82096c63c35ebf9c3d17cf6afc3f66ccaa8b4644`
- Backup of pre-patch production script:
  `work/_debug_c002_inspect/run_prompt_pack_production.py.bak_before_v5a_*`

## Tests
- `python -m unittest work.test_still_retry_not_stop` → **38 OK**
- `python -m unittest work.test_still_retry_not_stop work.test_image_render` → **53 OK**
- `python -m unittest local_agent.test_production_integrity` → **39 OK**

## Production status at patch time
- `paused_for_identity_recovery` after v4b max_attempts=1
- Accepted C001_last unchanged: `6e12ff2ab0b84085b765b7dd07a6bd4c`
  still SHA-256 `1302d430636908f50d6d3c2815559a7161300d9d2a5ab96320dd80c95260b4b6`
- No evidence deleted/overwritten

## Next
One bounded supervisor: `python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0`
(clears content pause itself). Expect v5a then automatic v5b; still-only;
GPU ceiling 82C; visual QA required. Do not start video.


## Live supervisor (bounded; stopped after C002_start accept)

Preflight: GPU ~30C, no live pack supervisor, Comfy :8188 down (supervisor starts owned backend), thermal emergency ceiling 82C.

Command: python work/run_prompt_pack_production.py --cid f8f7f70e364d40c0
- PID 47628; logs work/_debug_c002_inspect/supervisor_v5_stdout.log

### C002_start v5a attempt
- attempt id 372f98ca4b764521be5678ba8aed6b13
- still SHA-256 2b8136b57e710d1cac798757afc985532be99c7bd523421fc01f3570586b334f
- policy c002-raised-hand-erase-v5a / gnoise-prefill-sd-erase-v1
- VLM semantic **pass** (mechanical pass); ledger promoted C002_start
- Pixel checks: outside-mask vs prefill ~exact; protected face vs accepted C001_last **exact**; bright-teal count 0
- Visual: raised-hand hole filled (not a flat grey prefill slab); **no v5b ran** because v5a was accepted. Operator must still confirm natural hanging left arm / no missing-limb or wall smear before trusting VLM.
- Copy: work/_debug_c002_inspect/v5a_372f98ca_still.png

### Stop reason
Supervisor advanced to C002_last attempt 57490bab2f204edeb8d7b175ba72faa3 (render completed; QA not finished). Force-stopped PID 47628 + watchdog; set paused_for_identity_recovery. Incomplete C002_last attempt **preserved** (not deleted). No video started.

### Production now
- status paused_for_identity_recovery
- supervisor_pid None
- C002_start ledger: generated / semantic pass / approval pending (v5a plate)
- Still-only; formal hash-bound full-set approval still pending
