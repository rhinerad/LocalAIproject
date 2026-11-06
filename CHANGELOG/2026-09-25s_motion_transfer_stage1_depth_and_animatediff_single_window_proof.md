# 2026-09-25s — Motion transfer follow-up: depth maps + node schemas proven; real AnimateDiff-SDXL single-window generations ran and came out upside down; seven ablations pin the inversion on the union-promax ControlNet path (unresolved); the AnimateDiff path is one node pack short for multi-window clips

Continues `2026-09-25q` (Part 2). Id `s` was the duplicate claim noted there;
used here so it is not a gap. Same session; no operator decision has been
given, so **nothing was downloaded or installed**. Benign inputs only.

## 1. Pass 2 — pose + depth + live schemas + VRAM (`runtime/motion_transfer_20260925/pose_extract_poc.py --tag pass2`)

Owned backend, custom nodes on (`face_detail=True`), thermal 29 C at start.
Evidence: `pose_poc_manifest_pass2.json`, `pose_poc_pass2.log`,
`node_schemas_pass2.json`; pass-1 manifest preserved as
`pose_poc_manifest_pass1.json`.

- Fixed: `DepthAnythingV2Preprocessor` keeps `ckpt_name` under `optional` in
  the v3 schema; the pass-1 runner had looked in `required`.
- prompt `history status_str: success`; **72 files, all present with sha256**
  (24 `src_`, 24 `pose_`, 24 `depth_` under
  `outputs/stories/_comfy_output/mcp_test/pose_poc_20260925_pass2/`);
  64.7 s; backend ready in 219.9 s (cold custom-node import); **peak GPU
  memory 3 228 MiB** (nvidia-smi `memory.used` every 2 s, 32 samples, min
  346). Depth frame 1 checked at native size: man in the foreground, woman
  and bed mid-depth, wall far — clean.
- Live `object_info`: 3 735 node classes; every class the three approaches
  need is present (`WanVideoAnimateEmbeds`, `WanVideoVACEEncode`,
  `WanVideoVACEModelSelect`, `WanVideoModelLoader`, `WanVideoSampler`,
  `WanVideoDecode`, `DWPreprocessor`, `DepthAnythingV2Preprocessor`,
  `ADE_AnimateDiffLoaderGen1`, `ADE_StandardUniformContextOptions`,
  `IPAdapterUnifiedLoader`, `IPAdapterAdvanced`, `SetUnionControlNetType`,
  `ControlNetApplyAdvanced`, `VHS_LoadVideoPath`, `VHS_VideoCombine`, …;
  `schemas_absent: []`). Their input schemas are dumped for offline graph
  authoring.

## 2. AnimateDiff-SDXL generation proof (`runtime/motion_transfer_20260925/animatediff_v2v_poc.py`)

Graph (20 nodes): `VHS_LoadVideoPath` (02A clip, 8 fps) → `DWPreprocessor`
→ `SetUnionControlNetType(openpose)` on `controlnet-union-sdxl-1.0-promax` →
`ControlNetApplyAdvanced` (strength 0.8); `CheckpointLoaderSimple
RealVisXL_V5.0_fp16` → `ADE_AnimateDiffLoaderGen1` (+
`ADE_StandardUniformContextOptions` 16/4 pyramid) → `IPAdapterUnifiedLoader
"PLUS FACE (portraits)"` + `IPAdapterAdvanced` (weight 0.8, image = the
film's Kent Brentwood master reference, copied — not moved — to the owned
backend's input dir as `mt_poc_character_kent_v1.png`, sha256
`be5a186f…`) → `KSampler` (euler/normal, 20 steps, cfg 6, seed 20260925,
768×448) → `VAEDecode` → `SaveImage` frames + `VHS_VideoCombine` h264 mp4.
Every node's inputs and combo values are validated against the live
`object_info` before posting (classic and v3 `COMBO/options` shapes; a
negative check confirms it rejects bad values).

| run | frames | result |
|---|---|---|
| `pass1` (24 frames) | 24 | **failed at KSampler** after 155 s of model loading and pose extraction: `Control type ControlNet may not support required features for sliding context window; use ControlNet nodes from Kosinkadink/ComfyUI-Advanced-ControlNet`. That pack is **not installed**. Backend warm start 20.1 s. |
| `pass2_16f` (16 frames = one context window) | 16 | **complete**: prompt `4ea8f891-…`, history success, 123.1 s; 16 `frame_*.png` + `animatediff_00001.mp4` (h264, 768×448, 8 fps, 16 frames, 2.000 s, 164 367 B, sha256 `8d1ac5079de9…`), all with sha256 in `animatediff_v2v_manifest_pass2_16f.json`; **peak GPU memory 14 874 MiB of 16 303** (61 samples). GPU 30 → 42 C. |

**Visual check of `pass2_16f` (frames 1 and 16, native size): the whole
scene is rendered upside down.** Two people, teal cardigan, dark hair,
grey-haired woman, lamp, window — the content follows the pose maps and the
prompt and the identity leans toward the reference, but the frame is
vertically inverted while the pose input for the same frames is upright
(checked `pose_00016_.png`). So: the pipeline is mechanically proven (nodes,
weights, VRAM, timing, end-to-end file evidence) and **not** yet a usable
motion transfer. This is exactly why nothing here is promoted.

Ablation (`--motion hsxl`: `hsxl_temporal_layers.safetensors` with
`linear (HotshotXL/default)`, everything else identical): _see §2a below._

### 2a. Ablation results

| run | change vs `pass2_16f` | result | orientation |
|---|---|---|---|
| `pass3_hsxl` | motion module `hsxl_temporal_layers` + `linear (HotshotXL/default)` | complete: prompt `2c5dfb46-…`, 223.7 s, 16 frames + mp4 (370 784 B, sha256 `e45084e3c7c9…`), peak 14 846 MiB, backend warm start 93.5 s | **still upside down** (frame 1) — the motion module is not the cause |
| `pass4_nocn` | pose ControlNet removed (`--no-controlnet`), `mm_sdxl_v10_beta` | complete: prompt `d5bb0597-…`, 108.9 s, 16 frames + mp4 (134 421 B, sha256 `1b1b91a5e258…`), peak 12 926 MiB | **upright** — a Kent-like man (dark curly hair, moustache, teal cardigan) beside a bed, lamp, headboard; frames 1 and 16 near-identical, i.e. no reference motion without the ControlNet |
| `pass5_cn_novae` | ControlNet kept, `vae` link removed from `ControlNetApplyAdvanced` | complete: prompt `f20583b5-…`, 185.9 s, 16 frames + mp4 (164 365 B, sha256 `6d0d8bfb9c8b…`), peak 14 878 MiB | **still upside down**, frame 1 visually identical to `pass2_16f` (same seed) — the VAE link is not the cause |
| `pass6_noad` | motion module + context options removed (`--no-animatediff`), 4 independent frames, ControlNet + IP-Adapter kept | complete: prompt `a4eb5b7a-…`, 143.0 s, 4 frames + mp4 (95 785 B, sha256 `68ba21040ec8…`), peak 12 286 MiB | **upside down** — plain SDXL flips too, so the inversion is the union-promax ControlNet path with DWPose maps, not AnimateDiff |
| `pass7_noad_auto` | as pass6 but `SetUnionControlNetType(type=auto)` | complete: prompt `acafe897-…`, 149.3 s, 4 frames + mp4 (101 661 B, sha256 `ed2415b410b3…`), peak 12 254 MiB | **upside down** — the union type is not the cause |

**Conclusion of the ablations.** Seven owned-backend runs, all with real file
evidence. The only configuration that renders upright is the one with no
ControlNet at all (`pass4_nocn`), and it carries no reference motion. Every
run that applies `controlnet-union-sdxl-1.0-promax` to DWPose maps —
with either motion module, with plain SDXL, with or without the VAE link,
with `type=openpose` or `auto` — produces a vertically inverted scene whose
layout otherwise follows the pose maps and prompt. The pose maps themselves
are upright (`pose_*.png` checked). So the fault is in the union-promax
ControlNet conditioning path on this install (model file, its loader
handling in this ComfyUI build, or a preprocessing expectation of that
model), not in AnimateDiff-Evolved. **Unresolved.** Next isolations, in
order (each is one ~3-minute plain-SDXL 4-frame run with the existing
runner): (1) same union model with the pass-2 depth maps and
`type=depth` — flips → model/loader problem, upright → pose-specific;
(2) `DWPreprocessor scale_stick_for_xinsr_cn: enable` (xinsir union
models expect scaled sticks); (3) `controlnet-canny-sdxl-1.0-fp16` with a
Canny preprocessor as a non-union baseline; (4) the unlabeled
`controlnet/diffusion_pytorch_model.safetensors` is an SD1.5-size
diffusers ControlNet (340 F32 tensors, 1 378 MB, no union embedding) and is
not an SDXL option; (5) `ComfyUI-Advanced-ControlNet` (operator approval)
is required regardless for any clip longer than one context window.

## 3. Corrections landed from the proof

- `local_agent/motion_transfer.py`: the AnimateDiff approach now requires
  `ComfyUI-Advanced-ControlNet` (custom node; code, not weights) and its
  `why` text records the live error; `feasible_now` for that approach is
  therefore **False on this machine** until the pack is installed, while
  `download_gb_to_enable` stays 0. `node_classes` gains
  `ACN_AdvancedControlNetApply`.
- `gvd_tool_router/catalog_seed.py`: `animatediff_sdxl_pose_ipadapter_unvalidated`
  `disabled_reason` now says one window rendered live and names the missing
  pack.
- `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md`: §3a row for the
  absent pack with the verbatim error, §3c install row (git clone + restart,
  operator approval), §4 AnimateDiff row and short answer corrected.
- `test_motion_transfer_plan.py`: fake tree installs the pack; removing it
  flips the approach to not-feasible with exactly that one missing item;
  this-machine smoke asserts no missing weights and at most that pack
  missing; seed-reason assertion updated. `python -m unittest
  test_motion_transfer_plan test_gvd_tool_router`: **67 OK**
  (`runtime/motion_transfer_20260925/tests_part2_acn2.log`); after the final
  wording edits, those two plus `test_queued_analysis_honesty`: **89 OK**
  (`tests_final_s.log`). The full non-live suite was last run in full after
  25q (1631 OK); this entry changed only `motion_transfer.py` text,
  `catalog_seed.py` text, one test, docs and runtime scripts.

## 4. Measured facts for a future template / VRAM profile

| stage | peak GPU MiB | seconds | notes |
|---|---|---|---|
| DWPose + Depth-Anything-V2-L on 24 frames @ 512 | 3 228 | 64.7 | CPU bbox (~1.3 s/frame), GPU pose |
| AnimateDiff-SDXL 16×768×448, 20 steps, union CN + IP-Adapter | 14 874 | 123.1 | 1.4 GB headroom on this 16 GB card; output inverted (see §2a) |
| same with HotshotXL layers | 14 846 | 223.7 | inverted |
| AnimateDiff-SDXL 16 frames, IP-Adapter, **no** ControlNet | 12 926 | 108.9 | upright, no reference motion |
| plain SDXL 4×768×448, union CN + IP-Adapter | 12 254 – 12 286 | 143 – 149 | inverted |
| owned backend start | — | 219.9 cold / 20.1–21.6 warm | custom nodes on |

## Not done / next

- Root-cause the inversion: the ordered isolations at the end of §2a. Until then the AnimateDiff-SDXL path is *mechanically* proven and *not usable*.
- Nothing installed: `ComfyUI-Advanced-ControlNet` needs operator approval
  like any node install; the Wan weights decision in `TODO.md` stands.
- No template pinned, no registry profile written, no promotion.
