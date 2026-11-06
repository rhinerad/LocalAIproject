# 2026-09-25u — ComfyUI-Advanced-ControlNet installed (operator approval); 24-frame, two-window AnimateDiff-SDXL motion-transfer clips now render upright and follow the reference motion; identity drift is the remaining blocker

Continues `2026-09-25t`. Id claimed once with `scripts/next_changelog_id.py`.

## Approval

Operator, in chat, this session: "approve installing
ComfyUI-Advanced-ControlNet". That covers this one node pack. Nothing else
was downloaded or installed; the Wan 2.2 Animate / VACE decision in `TODO.md`
is unchanged.

## 1. Install

- `git clone https://github.com/Kosinkadink/ComfyUI-Advanced-ControlNet` into
  `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\custom_nodes\ComfyUI-Advanced-ControlNet`.
  Remote `HEAD` before cloning = cloned commit
  **`27a67fee80cf46c198b10588a5651f23d67d1e95`** (2026-07-28, "bump version
  1.6.0"; the installed AnimateDiff-Evolved `92576512` is from the same day).
  771 KB without `.git`.
- `pyproject.toml`: `dependencies = []`, `requires-comfyui = ">=0.3.68"`
  (install is 0.36.0). **Nothing pip-installed**, no other file in the ComfyUI
  tree changed (`git status` shows only the three untracked files that were
  there before). No pack was present before, active or under `.disabled/`.
- No restart was needed: every owned-backend run starts a fresh ComfyUI.
  Live `object_info` after install: **32 `ACN_*` classes**, including
  `ACN_AdvancedControlNetApply_v2` (current) and `ACN_AdvancedControlNetApply`
  (the older version).
- Why it matters (source read): AnimateDiff-Evolved's sliding context
  (`animatediff/sampling.py` `prepare_control_objects`) needs control objects
  with ACN's `sub_idxs`. With ACN installed, AD hooks ACN's outer sample
  wrapper (`model_injection.py` → ACN `sampling.py` `convert_all_to_advanced`),
  which converts core `ControlNet` objects to `ControlNetAdvanced`. `copy_to`
  keeps `extra_args`, so `SetUnionControlNetType`'s `control_type` survives,
  and each window gets its own hint slice (`cond_hint_original[sub_idxs]`).

## 2. Runner (`local_agent/runtime/motion_transfer_20260925/animatediff_v2v_poc.py`, CRLF kept)

`_edit_runner_25u_acn.py` (exact anchors, refuses a second run): `--acn-apply`
swaps node 20 to `ACN_AdvancedControlNetApply_v2` (`vae` → `vae_optional`);
the manifest records `acn_node_classes` from the live `object_info` and
`settings.acn_apply`. Defaults unchanged.

## 3. Runs (owned backend; preflight owner file + port 8188 + thermal; the operator's chat was idle and the chat model unloaded before starting; owner released after each)

24 frames at 8 fps = two 16-frame contexts, overlap 4, pyramid fuse;
AnimateDiff `mm_sdxl_v10_beta`; union promax `openpose` on DWPose body +
hands, **face off**, xinsir sticks (the 25t rule); RealVisXL, IP-Adapter PLUS
FACE 0.8 on the Kent reference copy, seed 20260925, 20 steps, 768×448.
Benign `02A` clip, read only.

| tag | apply node | prompt_id | history | backend start | render | peak GPU MiB | mp4 sha256 (h264 768×448, 24 frames, 3.000 s) |
|---|---|---|---|---|---|---|---|
| `pass15_ad24_core` | core `ControlNetApplyAdvanced` (the graph that failed in 25s `pass1`, with the 25t pose fix) | `04c1d336-dda7-4753-95d7-ec92de623de8` | success | 128.3 s | 282.7 s | 14 622 | `86e430c77ba00405fd80ba15c4aba1a53a3bc7adb86539224b486af79fcac6a0` |
| `pass16_ad24_acn` | `ACN_AdvancedControlNetApply_v2` | `0ec0b6ad-c8db-40b8-b9ab-d51bd60b68b4` | success | 118.9 s | 268.4 s | 15 902 | `552df63b537157e6cc0a5d3ddf56b034d43d1eb6309a4be22874ee5ff6532922` |

Each run: 72 output files (24 src, 24 pose, 24 frames), all present with
sha256 in `animatediff_v2v_manifest_<tag>.json`. GPU 29 → 46 C and 46 → 47 C.

- **The two runs are pixel-identical**: 24/24 frames `np.array_equal`, max
  absolute difference 0. The PNG files differ only because each embeds its own
  graph in `prompt` metadata. So the explicit ACN node and ACN's automatic
  conversion of the core node are the same computation here. The measured
  peak differed by 1.3 GB for identical output (allocator caching;
  `nvidia-smi` sampled every 2 s), so a VRAM profile must budget **~15.9 GB
  of 16.3 GB** at this size.
- **Visual check** (`contact_25u_pass15_24f.png`: all 24 source + generated
  frames; `contact_25u_pass16_24f.png`; frames 14 and 20 at native size):
  all 24 frames upright. Room, bed and reclining woman are continuous across
  the window seam (frames 13–16), with no jump. The standing man follows the
  reference (leans in, straightens, leans back in). **Identity fails:** from
  about frame 13 the standing man turns into an older, longer-haired,
  woman-like figure with a moustache, and frames are soft. Not a usable
  recast.
- Identity options on disk without a download: only
  `ip-adapter-plus-face_sdxl_vit-h` (no FaceID weights;
  `models/insightface/buffalo_1` is empty; `ipadapter/sdxl_models/` empty),
  so tuning is limited to IP-Adapter weight/type/embeds scaling and a
  face-cropped reference.

## 4. Planner, seed row, doc, TODO

`_edit_25u_text.py` (verifies every anchor before writing; line endings
kept) and `_edit_25u_vram.py`:
- `local_agent/motion_transfer.py` (LF): the AnimateDiff `why` says the pack
  is installed and multi-window clips render, and names identity drift as the
  open problem. `node_classes` `ACN_AdvancedControlNetApply` →
  **`ACN_AdvancedControlNetApply_v2`** (the current id). `frame_plan.suggested_size`
  **`1024x576` → `768x448`**: 1024×576 was never measured, and 768×448 already
  peaks at 15.9 GB. `vram_note` now carries the measurement.
- `local_agent/gvd_tool_router/catalog_seed.py` (LF):
  `animatediff_sdxl_pose_ipadapter_unvalidated` `disabled_reason` updated;
  the row **stays disabled** (no pinned template, no VRAM profile, identity).
- `docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` (CRLF): §3a / §3c / §4
  rows now "installed"; new §6d.
- `TODO.md` (CRLF): note under decision option (c).
- Live planner on the benign inputs
  (`runtime/motion_transfer_20260925/plan_25u_benign.json`; read only):
  `animatediff_sdxl_pose_ipadapter` **`feasible_now: true`, `missing: []`**,
  `recommended_now` = it, `best_with_download` = `wan22_animate_14b`; GVD
  route **`blocked`** (correct: no active implementation).

## 5. Tests

- `python -m unittest test_motion_transfer_plan test_gvd_tool_router
  test_queued_analysis_honesty`: **89 OK** (`tests_25u.log`).
- Full non-live suite from `local_agent/`
  (`python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')`):
  **Ran 1631 tests in 367.6 s, OK (skipped=2), exit 0** (`full_25u.log`),
  the same count as the 25q baseline.

## Not done / next

- **Identity** is the blocker for this approach. Next bounded experiments,
  no download: IP-Adapter weight 1.0 / `weight_type` variants /
  `embeds_scaling "K+V"`; a face-cropped reference instead of the full
  master. The better fix is a download (FaceID or Wan 2.2 Animate), which
  needs the operator.
- No pinned API template, no VRAM profile in the GVD registry, no promotion,
  no `render_video_from_reference` tool. A 3-second clip with the wrong
  person is not a validated capability.
- Full-length clips: the 8 s benign clip is 64 frames = 5 windows at this
  size; not run.
