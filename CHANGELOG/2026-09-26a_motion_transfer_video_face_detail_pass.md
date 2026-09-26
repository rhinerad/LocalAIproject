# 2026-09-26a — Motion transfer: an Impact Pack video face-detail pass on the AnimateDiff clip; no added flicker (measured), late frames move toward the reference at denoise 0.5; faces stay soft because they are ~60 px at 768×448

Continues `2026-09-25v`. Operator, in chat: "try the per-frame face-detail
pass first". Nothing downloaded or installed (Impact Pack and its subpack were
already present; the detector is the still renderer's
`bbox/face_yolov8m.pt`). Id claimed once with `scripts/next_changelog_id.py`
(the date rolled over during the session). Benign inputs only.

## 1. Graph (runner `animatediff_v2v_poc.py --face-detail`, CRLF kept)

`_edit_runner_25w_fd.py` (exact anchors, refuses a second run) adds, after the
decoded frames (node 23):

- `UltralyticsDetectorProvider bbox/face_yolov8m.pt` →
  `ImpactSimpleDetectorSEGS_for_AD` (threshold 0.5, crop factor 3.0,
  "Pivot SEGS" / "Combined mask": one region per face over all frames) →
  `ImpactSEGSOrderedFilter` (`x1` ascending, take 1: the leftmost face, the
  man; otherwise the Kent identity would be painted onto the woman too).
- `IPAdapterAdvanced` copy **without** the attention mask (the frame-space
  mask does not fit crop space), same face-crop reference and weight →
  `ToBasicPipe` with a face prompt → `DetailerForEachPipeForAnimateDiff`
  (guide 384, max 512, 20 steps, cfg 6, euler/normal, feather 8, noise-mask
  feather 20). Since the crop batch goes through the AnimateDiff model, the 24
  face crops are sampled together, not independently.
- Saves `fd_frame_*` + `animatediff_fd_*.mp4` beside the undetailed
  `frame_*` + mp4, so one run compares both. The runner waits on the detailed
  frames (node 48) and marks a run complete only with both frame sets. The
  manifest records the face-detail settings.
- First attempt used the Python class name `SimpleDetectorForAnimateDiff`;
  the runner's pre-post validation against live `object_info` refused it (no
  GPU work; manifests `pass20_fd035` / `pass21_fd050`, status `failed`,
  kept). The registered id is `ImpactSimpleDetectorSEGS_for_AD`
  (`comfyui-impact-pack/__init__.py:157`); fixed with a one-string anchored
  replace.

## 2. Runs (owned backend; operator chat idle and chat model unloaded; preflight owner + port + thermal; released after each)

Base = `pass18_id_face_mask` (24 frames, face crop, left-region mask, face
keypoints off, xinsir sticks, seed 20260925, 768×448).

| tag | fd denoise | prompt_id | whole prompt | peak MiB | detailed mp4 sha256 |
|---|---|---|---|---|---|
| `pass20b_fd035` | 0.35 | `08914fea-72df-4c02-a815-868a532944a8` | 557.0 s | 15 902 | `8c65bd83bf74c68842f5ffa14d1225256e14cd5b9bc5b1ab5c31ede28031e32c` |
| `pass21b_fd050` | 0.50 | `8a94f003-bd7c-4cbe-88be-5572d98b378e` | 526.8 s | 14 622 | `43ede612dad210b152730718a79c1fb9c454d2609fbeec1b30431d31bc7e9066` |

Each: history `success`, 96 files (24 src, 24 pose, 24 frame, 24 fd_frame)
present with sha256; two mp4s each. Backend start 21.7 s warm / 560.1 s cold
(the 900 s limit was needed). GPU 30–44 C.

**Determinism.** The undetailed frames of both runs are pixel-identical to
`pass18` and to each other (24/24 each). The two undetailed mp4s differ only
in embedded metadata. So every difference between `frame_*` and `fd_frame_*`
is the detail pass.

## 3. Measurements (`_fd_eval.py`; head region x 100–420, y 0–260; mean absolute RGB difference, 0–255)

| | 0.35 | 0.50 |
|---|---|---|
| detailed vs undetailed, head region | 1.40 | 1.83 |
| frame-to-frame change in head region, undetailed → detailed (mean) | 8.74 → 8.69 | 8.74 → 8.65 |
| same, max over the 23 steps | 21.07 → 20.55 | 21.07 → 20.50 |
| detailed vs undetailed outside the head region (max over frames) | 0.0 | 0.0 |

**No added flicker** at either level, and the paste touches nothing outside
the face region.

## 4. Visual check (native-resolution crops: `fd_eval_pass20b_fd035.png`, `fd_eval_pass21b_fd050.png`; late faces magnified 2× nearest-neighbour beside the reference crop: `fd_eval_late_faces_zoom.png`)

- Frames 1–8: essentially unchanged.
- Frames 14–20: some stubble and skin texture, slightly finer moustache.
- Frame 24 (the §6e drift): undetailed = a smooth, young face with a thick
  black moustache. At 0.35: stubble, thinner moustache. **At 0.50: raised
  brows (the reference's expression), an older, more lined face, a natural
  moustache, closest to the reference.**
- All faces stay soft: a face is ~60 px wide in a 768×448 frame, so detail
  resampled in the 512 px crop is lost when pasted back. Softness is now a
  resolution limit, not an identity one.
- My frame-level judgement; likeness acceptance is the operator's.

## 5. Text updated

`_edit_26a_text.py` (every anchor verified before any write; line endings
kept): `local_agent/motion_transfer.py` AnimateDiff `why`,
`gvd_tool_router/catalog_seed.py` seed reason (row stays disabled),
`docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` new §6f, `TODO.md` note.
`python -m unittest test_motion_transfer_plan test_gvd_tool_router
test_queued_analysis_honesty`: **89 OK** (`tests_26a.log`).

## Not done / next

- Softness: needs a larger output. Upscale-then-detail, or larger frames at a
  16-frame context: 768×448 already peaks at 14.6–15.9 GB, so larger sizes are
  VRAM-limited and unmeasured. Or a download (FaceID / Wan 2.2 Animate).
- Face selection by leftmost position fits only this clip. A template needs
  selection by the character's mask or pose box.
- Cost: face detail roughly doubles the per-clip time (527–557 s vs ~300 s
  for 24 frames).
- Still no pinned template, GVD VRAM profile, promotion, or
  `render_video_from_reference` tool.
