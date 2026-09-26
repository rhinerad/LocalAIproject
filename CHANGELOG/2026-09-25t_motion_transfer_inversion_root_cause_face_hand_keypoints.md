# 2026-09-25t — Motion transfer: the upside-down AnimateDiff-SDXL output is root-caused (DWPose face + hand keypoints drawn together, which xinsir's union model never saw); with face keypoints off, one 16-frame window renders upright and follows the reference motion

Continues `2026-09-25s` §2a ("Unresolved"). Id claimed once with
`scripts/next_changelog_id.py`. **Nothing downloaded or installed**; the Wan
decision in `TODO.md` is still the operator's. Benign inputs only (the Equal
Shares `02A` Stage-1 clip, read only; the Kent master reference copy already
in the owned input dir). Equal Shares state untouched.

## 1. Non-GPU checks (isolation d)

- **Core is upstream.** `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI` is
  at `ee71d5c4` "ComfyUI v0.36.0"; `git status` shows no modified tracked
  files (only untracked `ASTRA_PRE_UPGRADE_COMMIT.txt`, `optimization_report/`,
  `patch_fasth3_wf.py`). `comfy/cldm/cldm.py` `union_controlnet_merge` is the
  xinsir ControlNetPlus scheme (spatial mean → task embedding → transformer →
  per-channel alpha added back): nothing in it can flip the image spatially.
  `comfy/controlnet.py` `get_control` only resizes the hint (`common_upscale`,
  center crop).
- **No custom-node patch.** `grep -rE` over all 117 `custom_nodes/` packs for
  reassignment of `get_control` / `forward` / `set_cond_hint` /
  `union_controlnet_merge` / `common_upscale` on controlnet/cldm objects, or a
  `flip` on a hint: no match (a control grep for `def get_control|comfy.controlnet`
  finds the expected 21 files, so the search covers the tree).
- **The model file is genuine.** `controlnet-union-sdxl-1.0-promax.safetensors`:
  863 F16 tensors, `task_embedding [8, 320]`, 12 `transformer_layes`,
  `control_add_embedding`; 2 513 342 408 bytes; **sha256
  `9fae2e50cb431bfcbe05822b59ec2228df545ef27f711dea8949e9f4ed9f7cdc`, identical
  to the LFS oid Hugging Face publishes for
  `xinsir/controlnet-union-sdxl-1.0/diffusion_pytorch_model_promax.safetensors`.**
  (`controlnet-canny-sdxl-1.0-fp16`: 844 tensors, size equal to
  `diffusers/controlnet-canny-sdxl-1.0` fp16; its hash was not finished — see §5.)
- xinsir's `controlnet-openpose-sdxl-1.0` model card: trained on **thicker
  sticks** and **body-only** poses (`hand_and_face=False`); default-width lines
  "may be unstable". `comfyui_controlnet_aux`'s `scale_stick_for_xinsr_cn`
  implements the stick part only (×2 for this 736 px source).

## 2. Runner changes (`local_agent/runtime/motion_transfer_20260925/animatediff_v2v_poc.py`, CRLF kept)

Edit scripts `_edit_runner_25t.py`, `_b`, `_c`, `_d` (exact anchors, each
refuses a second run). Defaults are unchanged, so earlier passes reproduce.

- `--control pose|depth_maps|canny`: `depth_maps` loads PNGs with
  `VHS_LoadImagesPath` from `outputs/stories/_comfy_output/mcp_test/mt_depth_inputs_from_pass2/`
  — the 24 pass-2 depth maps **copied** (not moved) there because that node
  loads every image in a folder; all 24 copies sha256-match
  `pose_poc_manifest_pass2.json`. The manifest records each input's sha256.
  `canny` = core `Canny` (0.4/0.8) on the clip.
- `--cn-model union|canny` (canny = `controlnet-canny-sdxl-1.0-fp16`, no
  `SetUnionControlNetType`), `--xinsr-stick`, `--body-only`, `--no-face`,
  `--no-hands`, `--flip-hint` (diagnostic `ImageFlip`, not used),
  `--startup-timeout` (default 480 s as before). The manifest's `settings`
  records `control_source`, `cn_model`, the actual `controlnet`,
  `xinsr_stick`, `body_only`, `no_face`, `no_hands`, `flip_hint`,
  `control_inputs`.

## 3. Runs (owned backend, preflight: owner file + port 8188 + thermal; all released cleanly)

Same seed 20260925, prompt, RealVisXL, IP-Adapter PLUS FACE 0.8, union
strength 0.8, 768×448, 20 steps as 25s. "4f" = plain SDXL, 4 independent
frames (`--no-animatediff`). Every row: history `success`, every output file
present with sha256 in its manifest `animatediff_v2v_manifest_<tag>.json`,
mp4 h264 768×448 8 fps (ffprobe in the manifest).

| tag | control image | prompt_id | mp4 sha256 | peak MiB | orientation |
|---|---|---|---|---|---|
| `pass8_depth` | depth maps, union `type=depth`, 4f | — | — | — | **no render**: backend not listening within 480 s (cold custom-node import; see §5); clean stop, owner released 01:48:30Z |
| `pass8b_depth` | same, `--startup-timeout 900` | `ba8c9465-bc92-4657-9048-f2fe7eb5c074` | `da79c05b111e…` | 14 814 | **upright 4/4**, layout follows the depth map |
| `pass9_xinsr_stick` | DWPose body+hands+face, xinsir sticks, 4f | `bbcfb3cc-697b-4a11-9379-3c10831a866a` | `dde457e65cf8…` | 12 222 | **inverted 4/4** |
| `pass10_bodyonly_xinsr` | DWPose body only, xinsir sticks, 4f | `151c4a05-a3db-4bab-b189-54ff93d677eb` | `32471f792f57…` | 14 046 | **upright 4/4** |
| `pass11_bodyonly_thin` | DWPose body only, default sticks, 4f | `2245f6b8-5e66-4794-b0e2-8465153d9853` | `62fa78502194…` | 14 942 | **upright 4/4** |
| `pass12_noface_hands_xinsr` | DWPose body+hands, no face, xinsir sticks, 4f | `e28441d9-9310-400f-828f-a5c27297626d` | `e1c4ded71ed3…` | 12 222 | **upright 4/4** |
| `pass13_face_nohands` | DWPose body+face, no hands, default sticks, 4f | `043d1162-9f3f-4e9e-8780-196feeb9a708` | `a5960ffa0373…` | 14 302 | **upright 4/4**; frame 1 has a stray extra person lying across the bottom |
| `pass14_ad16_noface_xinsr` | **AnimateDiff `mm_sdxl_v10_beta`, 16 frames**, DWPose body+hands, no face, xinsir sticks (= `pass2_16f` with face off + xinsir sticks) | `09a7b6b3-e596-4dd3-9e8d-940113ff1139` | `ef9d521b9340b6ab303080809bb4d2e7d44db56a35b35285c902a494cda6a7d3` (145 754 B, 16 frames, 2.000 s) | 14 878 | **upright 16/16, follows the reference motion** |

Backend start 24.5 s warm to 316.6 s cold; renders 117–204 s; GPU 28–34 C
before/after the 4f runs, 31 → 42 C for the 16-frame run.

**Correction to 25s.** 25s judged each run on frame 1. Re-reading `pass6_noad`
on all four frames (`contact_25t_orientation.png`): frames 1, 3, 4 inverted,
**frame 2 upright**. The full-keypoint condition inverts most frames, not
every frame.

**Visual checks.** Frame 1 of `pass8b`, `pass9`, `pass10`, `pass12`,
`pass14` and frame 4 of `pass10` and 16 of `pass14` at native size; all four
frames of passes 6/8b/9/10/11/12 on `contact_25t_orientation.png`; pass 13
frames + pose maps on `contact_25t_pass13.png`; `pass14` source / pose /
generated frames 1, 6, 11, 16 on `contact_25t_pass14_motion.png`
(orientation is a large-area property and reads at reduced scale; faces were
judged only on native frames). In the source the man leans over the bed at
f1 and straightens up and back to the left by f16. The generated man does the
same, while the woman stays reclined and the room is stable across frames.

## 4. Root cause

The inversion appears **only when the DWPose map carries face and hand
keypoints together** (inverted 3/4 and 4/4). Removing either one (4/4
upright each), or both (8/8 upright), gives an upright scene that follows
the pose. Stick width makes no difference in either direction (pass9 vs
pass6, pass10 vs pass11). The union model reads depth correctly (4/4). So
this is an out-of-distribution control image for xinsir's union model
(trained body-only), not a model, loader, ComfyUI or AnimateDiff fault.
Scope of the evidence: one clip, one seed, 4 frames per condition (16 for
pass14). The rule for any template of this approach:
**`DWPreprocessor detect_face: disable`** (body-only is xinsir's documented
preparation; hands tested fine). Isolation (c), the non-union canny
baseline, was not run: (a) had already shown the union model is sound. The
runner supports it (`--control canny --cn-model canny`).

## 5. Operator-facing incident during this session

At 21:31:07 the operator's local-agent chat `df4d3c68cf9f4d87` ran
`render_story_image` (`fightclip_refvideo`). Its owned backend stalled during
Python/torch import and failed "startup deadline exceeded" after 302 s
(`work/runtime/agent_image_jobs/fightclip_refvideo_20260925_213107.log`;
owner released 01:36:18Z; no output). In the same minutes: the chat model
(`qwen3-abliterated:14b`, 14 GB, loaded from `A:\Users\rhine\.ollama\models`)
was loading, and **this session's `sha256sum` was reading 2.5 GB from the
same A: drive** (21:32–21:37). The drive measured 323 % busy, queue 3.2, 6.5
MB/s during the later cold start. My hash very likely contributed to their
startup timeout. Not proven. The canny hash was stopped part-way
(its `sha256sum.exe`, pid 31784, mine, was ended). No GPU run of this session
overlapped their job: I waited until their chat was idle, the model had
unloaded, the owner file was released and 8188 was free, and re-checked
before every run.

## 6. Text corrected

Edit script `runtime/motion_transfer_20260925/_edit_25t_text.py` (verifies
every anchor before writing any file; line endings kept):
- `local_agent/motion_transfer.py` (LF): AnimateDiff approach `why` now
  records the root cause and the `detect_face=disable` rule instead of
  "unresolved".
- `local_agent/gvd_tool_router/catalog_seed.py` (LF):
  `animatediff_sdxl_pose_ipadapter_unvalidated` `disabled_reason` likewise.
  The row stays disabled (no template, no VRAM profile, the node pack).
- `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` (CRLF): new §6c.
- `TODO.md` (CRLF): a note under decision option (c).

`python -m unittest test_motion_transfer_plan test_gvd_tool_router
test_queued_analysis_honesty` from `local_agent/`: **89 OK**
(`runtime/motion_transfer_20260925/tests_25t.log`). Full non-live suite not
re-run: this entry changed two text strings in non-test modules, a doc, TODO
and runtime scripts.

## Not done / next

- **Identity is weak.** Frame 1 of each pose run without face keypoints
  (passes 10–13) renders the standing figure as a grey-haired woman, not the
  reference. In pass14 the face is
  soft and the mouth/moustache region smudges by frame 16. The IP-Adapter
  (PLUS FACE at 0.8) needs work (FaceID, weight, or a face-detail pass)
  before this is a usable recast.
- Clips over 16 frames still need `ComfyUI-Advanced-ControlNet`
  (operator approval; not installed).
- No operator download approval yet, so step 2 (Wan template) did not start.
  No pinned template, VRAM profile, registry profile or promotion. No
  `render_video_from_reference` tool: one correct 2-second window is not a
  validated capability.
- The operator's failed `fightclip_refvideo` render (§5) was not retried by
  me. It is their job.
