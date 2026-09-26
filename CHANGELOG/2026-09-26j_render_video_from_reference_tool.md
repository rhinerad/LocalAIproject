# 2026-09-26j — `render_video_from_reference` + `video_reference_job_status` built: background motion-transfer jobs with the measured AnimateDiff/FaceID configuration, automatic face crop and target-person selection, render_story_image's GPU discipline, file-evidence manifests; validated end to end on two real runs

Operator, in chat: "build the render_video_from_reference tool". Continues
`2026-09-26g`. Id claimed once with `scripts/next_changelog_id.py`. Benign
inputs only (the Equal Shares `02A` Stage-1 clip, read only; the Kent master
reference copy in the owned input dir). Nothing downloaded or installed.

## 1. New files

- **`local_agent/motion_transfer_render.py`** (LF). Contents:
  - `prepare_request` validates a call (attestation, inputs, prompt, fps
    4–12, start/max seconds, target, frame cap) and probes both files with the
    planner's helpers.
  - `plan_frames`, `output_size`, `choose_target`, `map_x`, `band_to_pixels`.
  - `build_graph`, the pinned template: `template_sha256()` =
    `d2943a9ddabc9c4f1308461ca2a93921e1c73fed0c5e134d48e188620a1ffc8d`, pinned
    in the tests.
  - `validate_graph` against live `object_info`.
  - The job runner (`--job-dir`) and `job_status`.
- **`local_agent/motion_transfer_faces.py`** (LF). InsightFace helper, run with
  the ComfyUI venv, CPU only; it refuses unless `buffalo_l` is on disk.
  - `crop`: largest face → square 1.75× crop → 448 px (centre crop if no face).
  - `faces`: faces per sampled frame.
  - `score`: ArcFace identity per output frame, with its caveat.
- **`local_agent/test_motion_transfer_render.py`** (LF): **34 tests**
  (validation, caps, sections, portrait, the Equal Shares tree refusal, frame
  plan, target choice and tracking, coordinate mapping, graph wiring for every
  measured rule and fallback, the pinned template, graph validation, the GPU
  sampler, job status states, and tool refusals and launch with the gate,
  backend checks and Popen patched).

## 2. What a job does

The graph is the 25t–26g recommended configuration:
- **Pose:** DWPose body + hands with face keypoints off, xinsir sticks;
  union-promax openpose through `ACN_AdvancedControlNetApply_v2`.
- **Motion model:** AnimateDiff `mm_sdxl_v10_beta`, 16/4 pyramid context,
  RealVisXL, 20 steps, cfg 6, 768×448.
- **Identity, main pass:** IP-Adapter PLUS FACE 0.8 on the automatic face
  crop, with an attention mask over the target's band when more than one
  person is present.
- **Identity, detail pass:** Impact video face-detail (denoise 0.5) on the
  target face (by left-to-right rank, or the largest face for one person)
  through FaceID Plus V2 (loader on the AnimateDiff model, detail pass only).
  PLUS FACE is used when the still has no detectable face or FaceID is absent.

Target analysis samples 8 reference frames (ffmpeg), detects faces, picks
`target` and follows it by nearest centre. The band is the median Voronoi
interval (at least 25% wide), mapped through the centre crop to output
pixels.

Order of operations:
1. Claim the shared image-render owner (`_write_owner`, which refuses a live
   owner) **before** the CPU analysis, so a still render cannot slip in.
2. Analyse the inputs.
3. `preflight_execute` (Equal Shares owner, port 8188, thermal wait).
4. Owned backend, 900 s start limit.
5. Validate the graph against live `object_info`; post.
6. Wait (timeout 1800 s + 60 s per frame; the thermal ceiling is checked
   throughout) while a passive nvidia-smi sampler records peak memory and
   temperature.
7. Collect outputs with sha256 and ffprobe.
8. `verified_outputs` is true only if source = pose = generated (= detailed)
   = planned frames and the final mp4's `nb_frames` equals the plan.
9. Always stop the backend and release the owner.
10. On CPU: the identity score.
11. Write `manifest.json` ("acceptance: not accepted …").

## 3. Tool wiring (`local_agent/tools.py`, LF; `runtime/motion_transfer_20260925/_edit_tools_26h_render.py`, 6 exact anchors, mtime re-checked before writing — another session had last edited tools.py at 01:15)

- `render_video_from_reference`:
  - refuses a remote identity (desktop only);
  - `prepare_request`;
  - under `_IMAGE_RENDER_LAUNCH_LOCK`: `router.gpu_busy`, Equal Shares owner,
    port 8188 (same `_port_8188_refusal`), live image owner, and
    `gpu_gate.request("ComfyUI motion-transfer video render", key=motion_transfer:<video sha>)`;
  - `new_job`, `Popen(PY motion_transfer_render.py --job-dir …)` logging to
    `runner.log`, `record_launch(pid)`;
  - returns the job_id, frames, windows, size, an estimate, and a note that
    nothing exists yet.
- `video_reference_job_status`: read-only, in `CONCURRENCY_SAFE_TOOLS`.
- Render tool added to `_REMOTE_GPU_TOOLS` (so a phone call is labelled and
  then refused). Neither tool is in `remote_security.REMOTE_DEFAULT_TOOLS`
  (phones are default-denied). Category `gvd`; schemas added.
- `remote_security.py` (CRLF): both tools added to `GATED_REMOTE_TOOLS` beside
  `render_story_image` (a phone needs an explicit desktop grant; the render
  tool still refuses remote callers). Found by the full suite (§7).
  `agent.py` untouched.
- **The running GUI server imported the old `tools.py`; restart
  `local_agent\START_LOCAL_AGENT_GUI.ps1` to get the tools.**

## 4. Validation (through `tools.call`, as the agent calls it; `runtime/motion_transfer_20260925/tool_validation_26h*.py/.log`; operator chat idle, gate mode `allow`)

| | run 1: whole clip | run 2: section, final code |
|---|---|---|
| job | `mtr_20260926_094720_c5cf3a` | `mtr_20260926_100526_50da39` |
| request | defaults (target auto, face detail on) | `start_seconds 2, max_seconds 2, face_detail false, target left` |
| prompt_id / history | `c8d97e9a-0991-4d84-9d89-c2e995dd71c3` / success | `581777e0-46ad-4134-87a2-f4efe6e01474` / success |
| frames planned = source = pose = generated (= detailed) | 63 = 63 = 63 = 63 = 63 | 16 = 16 = 16 = 16 |
| final mp4 | `video_fd_00001.mp4`, h264 768×448 8 fps, 63 frames, 7.875 s, 729 466 B, sha256 `1f7a0012d65b8d6357592c7314dcf04a78740b27889867f4c741522a7de4312c` | `video_00001.mp4`, 16 frames, 2.000 s, 159 369 B, sha256 `eecd0a12795bafd99c2ef3cfee4b461c52b4d6ce8a85c4b5657bd2cf4ad3c769` |
| all outputs present with sha256 | 252 files | 48 files |
| backend start / render | 192.7 s / 574.8 s | 85.2 s / 199.8 s |
| GPU during render | not recorded (sampler added after run 1; nvidia-smi read 15 835 MiB, 67 C mid-run) | peak 14 587 MiB, 68 C (98 samples) |
| face crop (auto) | det 0.878, box (755, 23, 956, 224), matching the hand crop of 25v | same |
| target | 3 "people" (a face in a framed photo counted), rank 0 = the man, band 0–0.510 → mask x 0–392 | band 0–0.506 → x 0–388 |
| identity (ArcFace, caveat) | mean 0.172, min 0.076, 63/63 detected (same as 26g's p24, 0.173) | 0.027, min −0.087 (no detail pass; matches PLUS FACE alone) |

**Visual check** (`tool_26h_all_frames.png`: all 63 source + detailed
frames; `tool_26h_heads.png`: native head crops f1/16/32/48/63;
`tool_26h_b_frames.png`: all 16 of run 2):
- All frames upright, and the scene is continuous across the five windows.
- The man follows the source: leans in, straightens, lowers to sit by the bed.
- Frames 1–32 give a Kent-like man. In frames 48–63 the hair lengthens and
  the face softens (late-window drift).
- The untargeted woman renders with a darker complexion than the source in
  several frames (only the target is controlled).
- My frame-level judgement, not acceptance.

**After the validation runs** (unit-tested, not live-run): run 2's analysis
labelled `identity_adapter_detail: FaceID Plus V2` although face detail was
off; the label is now `None` when face detail is off.

## 5. Text updated (`_edit_26j_text.py`: anchors verified, mtime re-checked, line endings kept)

`local_agent/motion_transfer.py` AnimateDiff `why` (names the tool);
`docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md` §7–§8 replaced with
what was built, its limits and how to ask; `TODO.md` note.

## 6. Tests

`python -m unittest test_motion_transfer_render`: 34 OK. Full non-live
suite: see §7.

## 7. Full suite (`python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')` from `local_agent/`)

- First run (`runtime/motion_transfer_20260925/full_26j.log`): 1749 tests, **1 failure**:
  `test_remote_tool_allowlist.test_every_registered_tool_is_classified`, because the two new
  tools were in neither `REMOTE_DEFAULT_TOOLS` nor `GATED_REMOTE_TOOLS`. Fixed as in §3.
- After the fix (`full_26j_b.log`): **Ran 1749 tests in 359 s, OK (skipped=2), exit 0.**
  (The count includes other sessions' new tests since the 25u baseline of 1631.)

## Limits / not done

- At most **64 frames per job** until a longer run is measured. Sections
  rendered separately do not share a scene.
- Portrait 448×768 is unmeasured. Output is 8 fps with no audio or
  interpolation.
- Faces in pictures inflate the people count. People crossing paths can
  break the band or rank.
- Late-window identity drift; untargeted people are not controlled.
- No GVD VRAM profile or promotion (the router still reports
  `motion_reference` blocked), and the seed row stays disabled. Wan approaches
  not built.
- Content rule: the tool requires `likeness_attestation: true` and records it.
  It cannot verify it; the operator is responsible for inputs.
