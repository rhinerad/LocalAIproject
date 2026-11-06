# 2026-09-22i — GVD video-pipeline readiness: wan8, tile-video, FastH3 admission, duplicate QA

Offline code work plus two bounded receipt-gated smokes on the existing
Rockernow Comfy at :8188. No production video was started, no "Do not start
videos" gate was touched, no second backend was launched, and no models were
downloaded or deleted.

## 8-step Wan I2V (`wan22_i2v_8step_unvalidated`)

- New fixture `gvd_tool_router/fixtures/wan_i2v_8step_smoke.api.json`: the
  proven 4-step graph (fp16 T5 bf16 offload_device, tiled decode) with
  `steps: 8`. No other parameter changed.
- Live smoke accepted: 480×256, 5 frames, 8 steps. Peak used 11,674 MiB,
  baseline 508, **extra 11,166 MiB** (fits the 2,048 MiB headroom policy:
  11,166 + 2,048 = 13,214 < 15,831 free).
- The two earlier crashes recorded in `2026-09-22a` did not reproduce with the
  clean 8-step graph; Comfy stayed healthy through model load, T5 convert,
  sampling, and decode.
- Promoted via `apply_profile.py`; digest
  `ec8cd0706dee9187305a32f7d327619398c4c2b9eef80f9c5006a18f344f26e0`.
- Outputs: `gvd_tool_router/wan_i2v_8step_smoke_00001_.png` … `_00005_.png`.

## Phase 4 Wan tile-control video upscale (`wan21_tile_video_unvalidated`)

- New fixture `gvd_tool_router/fixtures/wan_tile_video_smoke.api.json`: exact
  API graph from the verified C016 rollout (`C016-verification.json`),
  including `VHS_LoadVideoPath` on `runtime/dspy_opt/br24_C016_00001_aud.mp4`,
  `umt5_xxl_fp8_e4m3fn_scaled` CLIP, tile LoRA 0.65, 4 steps uni_pc, denoise
  0.35, tiled VAE decode, silent-audio mux, `VHS_VideoCombine`.
- Live smoke accepted: 1280×720, 17 frames. Peak used 13,658 MiB, baseline
  506, **extra 13,152 MiB** (13,152 + 2,048 = 15,200 < 15,831 free). The
  resulting MP4 is 747,136 bytes, matching the proven C016 output
  (747,041 bytes) from the same input and graph.
- Promoted via `apply_profile.py`; digest
  `e5d2bc073f7754be7d9b2ca3e04e61101698bc53edef3d83f2ba2fada5a936e0`.
- Outputs: `gvd_tool_router/wan_tile_video_smoke_00001.mp4`.

## FastH3 V2 admission (`fasth3_v2_unvalidated`)

- Seed catalog now sets `extra_limits.requires_operator_approval: true` for
  `fasth3_v2_unvalidated` (peak 14,889 MiB cannot admit under the standard
  2,048 MiB headroom on the 16 GiB card).
- `switch_to()` gained an `operator_approval` parameter: an approved call may
  use a 512 MiB headroom floor (never zero). The returned admission record
  reports `headroom_mib` and `operator_approval`.
- `router._select_profile()` applies the same rule for flagged
  implementations; `service.route_shot()` accepts
  `operator_approved_resource_override` on a dict manifest and passes it
  through. The 2,048 MiB default is unchanged for every other profile.
- Verified by direct calls: standard → `RESOURCE_BLOCKED`; with approval →
  `local_smoke_h3v2`. Re-promoted with the flag; digest
  `c495262e00d99533fdedfecc764686b0b4af267104e5fac1ac1ac98395094280`.
- LongCat stays disabled and is not in the active registry.

## Semantic QA: duplicate-generation detection

- New `gvd_qa/duplicate.py`: caption token-Jaccard overlap plus a perceptual
  dhash fingerprint (Pillow, `get_flattened_data` with older-Pillow fallback).
- `evaluate_artifact()` accepts `artifact_bytes` and `prior_artifacts`
  ((caption, image) pairs) and reports
  `duplicate_caption_and_fingerprint` / `duplicate_caption` reasons with
  per-prior evidence. Duplicates hold review (never auto-reroll): the cause
  must be diagnosed before any bounded retry.
- Thresholds in `gvd_qa/constants.py`: `DUP_CAPTION_OVERLAP_MAX = 0.85`,
  `DUP_DHASH_MAX_DISTANCE = 8`. Same caption with a visibly different
  fingerprint is not flagged.
- New `test_gvd_qa_duplicate.py`: 12 CPU-only tests.

## Verification

- `python -m unittest test_gvd_qa_duplicate` — 12/12 OK.
- `python -m unittest test_gvd_tool_router` — 29/29 OK.
- QA + router family sweep (`test_gvd_qa*`, `test_router_*`,
  `test_gpu_vram_num_ctx`) — 182/182 OK (106 s).
- `py_compile` clean on every touched module.
- Registry inspection confirms the three active profiles, their measured
  peaks, and the FastH3 approval flag.

## Not changed

- No production video starts; the "Do not start videos" and 204-still
  approval gates are untouched and still bind.
- The router planner's conservative hardcoded free-VRAM inventory in
  `execute_tool()` was not raised.
- Older harnesses (`localagent/`, `local-agent-core/`) and LongCat remain as
  they were.
