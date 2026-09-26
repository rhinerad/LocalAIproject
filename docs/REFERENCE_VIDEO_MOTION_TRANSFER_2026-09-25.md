# Reference-video motion transfer with character replacement — what this install can do (2026-09-25)

Written with `CHANGELOG/2026-09-25q_queued_analysis_honesty_and_motion_transfer_plan.md`.
Investigation of the request in `local_agent/chats/1f0e3e61bdb0487a.json` msg 0
(now under `chats/_deleted/`, evidence preserved): take a reference video, keep
its motion for its whole length, and put a different character, supplied as a
still, into it — "for MiniMax". The operator has said this kind of recasting of
*any* reference video is an ongoing need.

**Short answer.** Nothing in this tree does it today, and MiniMax H3 cannot do
it at all (its conditioning is stills, references and audio, not a motion
clip). Three ComfyUI approaches exist for this machine. One has every weight installed
right now (lowest quality; one node pack short of multi-window clips). The two better ones each need one weight file that
is not on disk, so they need the operator's download approval. What shipped in
this pass is the honest plumbing: the GVD router now knows the capability and
names exactly what is missing, a read-only planner tool reports the same per
approach with sizes, and the first stage every approach shares — turning the
reference clip into per-frame pose and depth maps — was run for real on a
benign clip through the owned ComfyUI backend (see §6). No generation path was
built; §7 says what a real `render_video_from_reference` still needs.

## 1. Why no existing path fits

| existing path | what it takes as motion input | why it cannot recast a reference video |
|---|---|---|
| `render_story_image` → Minimax FLF2V / `run_prompt_pack_production` | a first and a last **still** | motion is invented between two frames; a 70 s reference has thousands |
| MiniMax H3 `ref2va` / `fl2va` (Equal Shares) | reference **images** + audio + text | no video conditioning input exists on those nodes |
| `comfy_generate` (comfyui-mcp `generate_image`, action `video`) | whatever graph comfyui-mcp composes | it composes its own graph; no pose/reference-video control |
| `analyze_video` / `extract_video_actions` (+ 25c camera estimator) | — | analysis only: words and measured camera moves, not a conditioning signal |
| `repair_video` (ProPainter) | a clip + mask | inpainting/completion; weights are on disk (150 MB) but the GVD gate keeps it blocked without a VRAM profile |

## 2. Content note for this specific request

`analyze_video` completed on the reference (media job `9603cd9abe114ed1`,
72 per-second observations): it is sexually explicit 3D animation. The
character still is an AI-generated nude turnaround sheet labelled "Bulma", a
fictional adult anime character, 1280×720. Everything in this pass was verified
only on benign material (an Equal Shares Stage-1 clip). The capability is
general; nothing here is tuned to that request. A real, identifiable person's
likeness must never be put into sexual content with these tools, and the
planner does not check for that — the operator is responsible for the inputs.

## 3. What is installed (measured 2026-09-25, `A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI` + `A:\Users\rhine\ComfyUI-Shared\models`)

GPU: NVIDIA GeForce RTX 5080, 16 303 MiB. ComfyUI was not running during the
inventory; `gvd_inventory`/router state was read from disk.

### 3a. Custom node packs that matter here (present unless marked)

| pack | gives | state |
|---|---|---|
| `ComfyUI-WanVideoWrapper` (kijai) | `WanVideoAnimateEmbeds`, `WanVideoVACEEncode`, `WanVideoVACEModelSelect`, `WanVideoUni3C_*`, `WanVideoControlEmbeds` | node code present; **no Animate / VACE / Uni3C / Fun-Control weights** |
| `comfyui_controlnet_aux` | `DWPreprocessor`, `OpenposePreprocessor`, `DepthAnythingV2Preprocessor` | present; DWPose (`yzd-v/DWPose/yolox_l.onnx` 207 MB, `hr16/DWPose-TorchScript-BatchSize5/dw-ll_ucoco_384_bs5.torchscript.pt` 129 MB) and Depth-Anything-V2-Large (1 279 MB) **already cached** under `ckpts/` — no first-use download |
| `ComfyUI-AnimateDiff-Evolved` | `ADE_AnimateDiffLoaderGen1`, `ADE_StandardUniformContextOptions`, … | present (v3 `io.ComfyNode` schema) |
| `comfyui_ipadapter_plus` | `IPAdapterUnifiedLoader`, `IPAdapterAdvanced`, `IPAdapterFaceID` | present |
| `ComfyUI-VideoHelperSuite` | `VHS_LoadVideoPath`, `VHS_VideoCombine` | present |
| core `SetUnionControlNetType` / `ControlNetApplyAdvanced` | union ControlNet type select | present (`comfy_extras/nodes_controlnet.py`) |
| `ComfyUI-Advanced-ControlNet` (Kosinkadink) | ControlNet apply nodes that AnimateDiff-Evolved's sliding context window accepts | **installed 2026-09-25 with operator approval** (commit `27a67fee`, v1.6.0, no Python dependencies; §6d). Before that, live 2026-09-25, 24 frames over a 16-frame context: KSampler failed with "Control type ControlNet may not support required features for sliding context window; use ControlNet nodes from Kosinkadink/ComfyUI-Advanced-ControlNet". Code only, no weights; a `git clone` into `custom_nodes/` after operator approval. Clips of one context window (16 frames) work with core nodes. |
| `ComfyUI-LTXVideo`, `ComfyUI-FramePackWrapper`, `ComfyUI-PainterI2V/LongVideo` | other video models | present, but none takes a pose/motion control video with these weights |
| `ComfyUI_ProPainter_Nodes` | video inpainting | present **with weights** (`weights/ProPainter.pth` 150 MB, raft 20 MB, flow completion 19 MB); GVD keeps `repair_video` blocked pending a local VRAM profile — that is a gate, not a missing install |
| `comfyui-advancedliveportrait` (+ `models/liveportrait/`) | face reenactment | present; head/face only, not body motion |
| `ComfyUI-segment-anything-2` (+ `models/sam2/` tiny/small) | masks | present; useful for Wan-Animate replacement mode |

### 3b. Weights present that the three approaches can use

| folder | file | MB |
|---|---|---|
| diffusion_models | `wan2.1_t2v_1.3B_fp16.safetensors` | 2 707 |
| diffusion_models / unet | Wan 2.2 I2V 14B high/low (fp8 scaled, fp16, Q4/Q5/Q8 GGUF, several NSFW finetunes) | 9 205 – 14 693 each |
| text_encoders | `umt5_xxl_fp8_e4m3fn_scaled` 6 424, `umt5-xxl-enc-fp8_e4m3fn` 6 424, `umt5_xxl_fp16` 10 840, `umt5-xxl-encoder-Q8_0.gguf` 5 763 | |
| vae | `wan_2.1_vae` 242, `Wan2_1_VAE_bf16` 484, `wan2.2_vae` 1 344 | |
| clip_vision | `clip_vision_h` 1 206, `CLIP-ViT-H-14-laion2B-s32B-b79K` 1 206 | |
| checkpoints (SDXL) | `sd_xl_base_1.0_0.9vae`, `RealVisXL_V5.0_fp16`, `dreamshaperXL_lightningDPMSDE`, `realismIllustriousBy_v55FP16`, … | 6 617 each |
| animatediff_models | `mm_sdxl_v10_beta.ckpt` 906, `hsxl_temporal_layers.safetensors` 905 | |
| controlnet | `controlnet-union-sdxl-1.0-promax` 2 397, `controlnet-canny-sdxl-1.0-fp16` 2 386, `mistoLine_rank256` 739, `wan2.1_tile_control` 361 | |
| ipadapter | `ip-adapter-plus-face_sdxl_vit-h` 808 | |
| insightface | `inswapper_128.onnx` 529 | (face swap; not used by the three approaches) |

### 3c. Weights **not** on disk (searched every configured model folder, `find -iname` over `ComfyUI-Shared/models`)

| what | needed by | approx size | where |
|---|---|---|---|
| `Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors` (or the bf16 / e5m2 variants) | Wan 2.2 Animate | ~17 GB fp8 (bf16 ~34 GB) | `huggingface.co/Kijai/WanVideo_comfy_fp8_scaled` → `Wan22Animate/`; original `Wan-AI/Wan2.2-Animate-14B` |
| `Wan22_relight_lora_fp16.safetensors` | Wan 2.2 Animate replacement-mode relighting (optional) | ~0.6 GB | `huggingface.co/Kijai/WanVideo_comfy` → `Wan22Animate/` |
| `Wan2_1-VACE_module_1_3B_bf16.safetensors` | Wan 2.1 VACE 1.3B (attaches to the 1.3B T2V already here) | ~1.2 GB | `huggingface.co/Kijai/WanVideo_comfy` → `VACE/`; alternative full model `wan2.1_vace_1.3B_fp16` ~6.7 GB at `Comfy-Org/Wan_2.1_ComfyUI_repackaged` |
| Wan 2.1 VACE 14B module / Wan 2.2 Fun A14B Control / Uni3C controlnet | higher-quality VACE / Fun-Control variants | 14B module ~5 GB on top of a 14B T2V (not present; ~14 GB); Fun Control ~2×14 GB; Uni3C ~1.5 GB | not recommended first; the two rows above cover the need |
| `ComfyUI-Advanced-ControlNet` custom node pack | AnimateDiff SDXL path for any clip longer than one 16-frame context window | ~1 MB of code (no weights) | **installed 2026-09-25u** (operator approval): `github.com/Kosinkadink/ComfyUI-Advanced-ControlNet` cloned into `custom_nodes/` |
| AnimateDiff SD1.5 motion modules + SD1.5 OpenPose ControlNet | an SD1.5 AnimateDiff variant | ~1.8 GB + 1.4 GB | not needed: the SDXL stack is complete |

## 4. The three approaches, for the operator's actual clip (70.767 s, 60 fps, 1920×1080, 4 246 frames)

Frame plans are what `plan_video_from_reference` printed for these inputs
(`local_agent/runtime/motion_transfer_20260925/plan_live.json`).

| approach | feasible now | download to enable | output plan | expected quality | VRAM (16 GB) |
|---|---|---|---|---|---|
| **Wan 2.2 Animate 14B** — `WanVideoAnimateEmbeds` + DWPose (+ face crops, SAM2 masks for replacement mode) | **no** | ~17 GB (+0.6 GB optional relight LoRA) | 16 fps → 1 133 frames in 15 overlapping 81-frame windows at 832×480 | best fit: purpose-built for "animate this character with that clip's body and face motion", replacement mode keeps the reference scene | 14B fp8 with WanVideoWrapper block swap already runs Wan 2.2 I2V here; Animate adds per-window embeds — **unmeasured**, needs a local VRAM profile |
| **Wan 2.1 VACE 1.3B** — `WanVideoVACEEncode` with DWPose control video + reference image | **no** | ~1.2 GB | 16 fps → 1 133 frames / 15 windows at 832×480 | real pose-driven v2v with identity from a reference image; 1.3B is visibly softer than 14B | comfortable; unmeasured |
| **AnimateDiff SDXL + ControlNet union (openpose/depth) + IP-Adapter Plus Face** | **yes: every weight and node pack installed; 24-frame multi-window clips render upright and follow the motion (§6d); identity drifts** | 0 GB (node pack installed 2026-09-25u) | 8 fps → 567 frames in 47 sixteen-frame contexts at 768×448 | lowest: SDXL motion modules flicker over long clips; identity comes from a face adapter, not full-body reference; full-body character sheet is only partly used | measured in §6 |

Any of the three, once its weights exist, still needs what every GVD
implementation needs before it may be offered as a tool: a pinned ComfyUI API
template, a measured local VRAM profile (`gvd_tool_router/apply_profile.py`
path), a validation render, and promotion. The disabled catalog rows for all
three exist now so that state is visible rather than implied.

## 5. What shipped in this pass (2026-09-25q)

- **GVD router knows the capability.** `CAPABILITY_MOTION_REFERENCE =
  "motion_reference"`, `ShotManifest.motion_reference_video`,
  `required_capabilities()` adds it (and `identity_reference` when a character
  is named). A blocked `gvd_route_shot` now returns `missing_capabilities`
  and `blocked_candidates` — the catalog/seed rows that carry a missing
  capability, each with `status`, `disabled_reason` and provenance — instead
  of a bare `UNAVAILABLE_CAPABILITY`. Three disabled seed rows:
  `wan22_animate_14b_unvalidated`, `wan21_vace_1_3b_unvalidated`,
  `animatediff_sdxl_pose_ipadapter_unvalidated`. `discover_workflows` accepts
  `motion_reference`.
- **`plan_video_from_reference`** (`local_agent/motion_transfer.py`, tool
  wrapper in `tools.py`; read-only, concurrency-safe, phone-visible). Input: a
  reference video and a character still. Output: ffprobe facts + sha256 of
  both, per-approach `feasible_now` / `installed` / `missing` (with sizes and
  download locations) / frame plan for the whole clip, `recommended_now`,
  `best_with_download`, `operator_decisions_needed`, and the GVD route
  decision. It never renders, starts ComfyUI, loads a model, or downloads.
  Presence checks go through the same resolver the still renderer uses
  (`work/image_render.model_file_on_configured_paths` over
  `work/runtime/image_render_model_paths.yaml`) plus the checkout's
  `custom_nodes/` tree.
- Tests: `local_agent/test_motion_transfer_plan.py` (GVD capability, blocked
  report, seed rows, planner inventory against a fake tree, frame plan,
  whole plan, tool wrapper, this-machine smoke).

## 6. Verified for real: stage 1, pose + depth extraction (owned backend)

Runner `local_agent/runtime/motion_transfer_20260925/pose_extract_poc.py`;
evidence `pose_poc_manifest.json`, `pose_poc.log`. Same owned-backend
lifecycle as `work/image_render.py` (owner file, port 8188 check, thermal
guard at 31 C, clean start with custom nodes enabled, clean stop, owner
released; `comfy_listening` False afterwards).

- Input: Equal Shares Stage-1 clip `ComfyUI-Shared/output/story/02A/attempt_1_00001_.mp4`
  (read only; sha256 `dd105c22864cd616…`, 8 s, 24 fps, 736×416, two people at a bedside).
- Graph: `VHS_LoadVideoPath` (force_rate 8, cap 24) → `DWPreprocessor`
  (`yolox_l.onnx` + `dw-ll_ucoco_384_bs5.torchscript.pt`, body + hands + face,
  512) → `SaveImage`; source frames saved beside the pose maps.
- Result: prompt `c6737c84-3706-4771-ae5c-90a125b32bda`, history `success`,
  47.3 s after a 2 min 52 s backend start; **48 files, all present with
  sha256 in the manifest** (24 `pose_*.png`, 24 `src_*.png`) under
  `outputs/stories/_comfy_output/mcp_test/pose_poc_20260925/`. No download:
  the cached DWPose weights were used ("Bbox ~1 330 ms, Pose ~60 ms on 4
  people" per frame in the backend log).
- Visual check, frame 1 at native size: two body skeletons matching the man
  leaning in from the left and the woman reclining right-of-centre, with
  face and hand keypoints; one tiny spurious skeleton at far right where
  DWPose read the framed family photo on the nightstand. Real templates need
  a mask or a bbox size floor for pictures-within-the-picture.
- Not run: the depth pass. `DepthAnythingV2Preprocessor` is present in live
  `object_info` (3 735 nodes, every class in §3a confirmed present), but the
  runner looked for `ckpt_name` under `required` and it lives under
  `optional`; the runner is fixed but was not re-run. Nothing was generated.

### 6b. Depth maps, live schemas, and a real generation attempt (CHANGELOG 2026-09-25s)

- Pass 2 of the extraction runner added Depth-Anything-V2-Large maps (24
  clean depth frames, checked), dumped the live `object_info` schemas of every
  node class the three approaches use (`local_agent/runtime/motion_transfer_20260925/node_schemas_pass2.json`),
  and measured stage 1 at **3 228 MiB peak GPU memory, 64.7 s** for 24 frames.
- `animatediff_v2v_poc.py` then rendered the AnimateDiff-SDXL path for real
  (RealVisXL + `mm_sdxl_v10_beta` + union-promax `openpose` on DWPose maps +
  IP-Adapter PLUS FACE on the Kent master reference, 16 frames at 768×448,
  20 steps): **complete, 123 s, peak 14 874 MiB of 16 303**, mp4 + frames
  with sha256s. The 24-frame attempt before it failed at the sampler because
  AnimateDiff-Evolved's sliding context window refuses core ControlNet nodes
  (`ComfyUI-Advanced-ControlNet` required; not installed).
- **The generated scene is upside down.** Seven ablation runs (HotshotXL
  layers; no ControlNet; ControlNet without the VAE link; plain SDXL without
  AnimateDiff; union `type=auto`) show the only upright output is the one
  with no ControlNet at all, which carries no reference motion. The
  inversion is in the union-promax ControlNet conditioning path on this
  install and is **unresolved**; ordered next isolations are in the 25s
  changelog. Until it is, the AnimateDiff-SDXL path is mechanically proven
  and not usable, and §4's "one context window renders today" means "runs",
  not "produces a correct clip".

### 6c. The inversion, root-caused (CHANGELOG 2026-09-25t)

Eight more owned-backend runs with the same seed, prompt, checkpoint and
IP-Adapter as 6b (plain SDXL, 4 independent frames, unless noted):

| control image | orientation |
|---|---|
| union `type=depth` on the pass-2 Depth-Anything-V2 maps | upright 4/4 |
| DWPose body + hands + face, xinsir-scaled sticks | inverted 4/4 |
| DWPose body + hands + face, default sticks (pass6 of 6b, re-read on all frames) | inverted 3/4 (frame 2 upright) |
| DWPose body + hands, no face, xinsir sticks | upright 4/4 |
| DWPose body + face, no hands, default sticks | upright 4/4 (frame 1 has a stray extra person) |
| DWPose body only, xinsir sticks / default sticks | upright 8/8 |
| **AnimateDiff `mm_sdxl_v10_beta`, 16 frames, body + hands, no face, xinsir sticks** | **upright 16/16, follows the reference motion** |

So the union-promax model, its loader, and ComfyUI's union code are fine
(core is unmodified upstream v0.36.0, no custom node patches the ControlNet
path, the file is byte-identical to xinsir's published
`diffusion_pytorch_model_promax.safetensors`, sha256 `9fae2e50…7cdc`). The
inversion appears only when the DWPose map carries face **and** hand
keypoints together, input the model was not trained on (xinsir's card:
body-only poses, thick sticks). Stick width makes no difference. **Any
template for this approach must set `DWPreprocessor detect_face: disable`**
(body-only is xinsir's documented preparation; hands may stay). Still
open for this approach: identity (the face IP-Adapter drifts on some
frames: a grey-haired woman instead of the reference in frame 1 of each
no-face pose run), SDXL softness, and clips longer than 16 frames need the
`ComfyUI-Advanced-ControlNet` pack (operator approval). Evidence:
`local_agent/runtime/motion_transfer_20260925/animatediff_v2v_manifest_pass8b…pass14*.json`,
`contact_25t_*.png`.

### 6d. Multi-window clips after installing ComfyUI-Advanced-ControlNet (CHANGELOG 2026-09-25u)

Installed with operator approval: `git clone` of
`github.com/Kosinkadink/ComfyUI-Advanced-ControlNet` into `custom_nodes/`,
commit `27a67fee80cf46c198b10588a5651f23d67d1e95` (v1.6.0, 2026-07-28), 771 KB,
`dependencies = []` (nothing pip-installed), `requires-comfyui >= 0.3.68`.
The live backend registers 32 `ACN_*` classes, including
`ACN_AdvancedControlNetApply_v2` (current) and `ACN_AdvancedControlNetApply`
(the older version).

- 24 frames at 8 fps (two 16-frame windows, overlap 4), AnimateDiff
  `mm_sdxl_v10_beta`, union openpose, DWPose body + hands with face off,
  xinsir sticks: the exact graph that failed in 6b now completes with the
  **core** `ControlNetApplyAdvanced`, because AnimateDiff-Evolved hooks
  ACN's sampling wrapper, which converts core ControlNets. The explicit
  `ACN_AdvancedControlNetApply_v2` gives **pixel-identical** frames (24/24,
  max difference 0).
- All 24 frames upright. Room, bed and reclining woman stay continuous
  across the window seam, and the standing man follows the reference
  (lean, straighten, lean back in).
- **Identity drifts:** from about frame 13 the standing man becomes an
  older, longer-haired, woman-like figure with a moustache (frames 14
  and 20 checked at native size); frames are soft. Only the PLUS FACE
  SDXL IP-Adapter is on disk (no FaceID weights, `insightface/buffalo_1`
  empty), so without a download identity can only be tuned by IP-Adapter
  weight/type and a face-cropped reference.
- Render 268–283 s for 24 frames; measured peak GPU memory 14 622 and
  15 902 MiB for the two pixel-identical runs, so budget ~15.9 GB of
  16.3 GB for this window size.

### 6e. Identity tuning without a download (CHANGELOG 2026-09-25v)

Cause of the drift: the character still was the full-body Kent master
(1672×941, lobby background). The PLUS FACE IP-Adapter's CLIP-ViT-H encoder
center-crops to a square and resizes to 224 px, leaving the face about
15 px across. Three 24-frame runs (same settings as §6d, one change each):

| change | identity (native-resolution head crops, frames 1/8/14/20/24) |
|---|---|
| baseline (§6d, full-body master) | drifts from frame ~13 into a long-haired, woman-like figure |
| **448×448 face crop** of the master (new file; original untouched) | **holds**: short dark hair, receding hairline, moustache, frames 1–20; frame 24 rounder/younger, moustache exaggerated; room picks up the crop's warm brown background |
| + IP-Adapter `attn_mask` over the man's region (left 400 of 768 px) | same man; the brown bleed stays on the left and the woman's side returns to the baseline palette |
| + weight 1.0 and `embeds_scaling K+V` | nearly indistinguishable from the row above; strength is not the limit |

Rule for a template: **pass a tight, square face crop, not the full
character sheet**, and mask the IP-Adapter to the character's region when
other people share the frame (a real template needs a per-frame mask, e.g.
from the DWPose person boxes; the static left-half mask only fits this
clip). Still open: softness, and the face drifting when the head turns
late in the clip (the only reference is face-on). The film's ensemble
master shows Kent face-on at ~60 px, so it adds no new angle. Next levers
need either a per-frame face-detail pass (a larger build, flicker risk) or
a download (FaceID, or Wan 2.2 Animate).

### 6f. Video face-detail pass (CHANGELOG 2026-09-26a)

Impact Pack, already installed: `UltralyticsDetectorProvider bbox/face_yolov8m.pt`
(the still renderer's detector) → `ImpactSimpleDetectorSEGS_for_AD` (one region
per face over all frames, "Combined mask") → `ImpactSEGSOrderedFilter` (leftmost
face only, so the character identity is not painted onto other people) →
`DetailerForEachPipeForAnimateDiff` through the same AnimateDiff model plus a
mask-free IP-Adapter copy (face crop), crop ≤ 512 px, 20 steps. Same run also
saves the undetailed frames, which reproduce §6e's run exactly (24/24
pixel-identical), so every difference is the detail pass.

| denoise | head-region change vs undetailed (0–255) | frame-to-frame change in head region (undetailed 8.74) | outside the head |
|---|---|---|---|
| 0.35 | 1.40 | 8.69 | 0.0 |
| 0.50 | 1.83 | 8.65 | 0.0 |

No added flicker at either level. Frames 1–8 barely change; 14–20 gain
stubble and texture; frame 24 improves most: at 0.50 the exaggerated
moustache and young, smooth face become an older face with raised brows and
a natural moustache, closer to the reference. Faces stay soft because a face
is ~60 px in a 768×448 frame; detail cannot survive being pasted back at that
size. Cost: the whole prompt 527–557 s for 24 frames (vs ~300 s without).
Softness is now a resolution problem, not an identity one: a larger output
(upscale then detail; VRAM-limited at 16-frame context) or a download.

### 6g. IP-Adapter FaceID Plus V2 (operator-approved download; CHANGELOG 2026-09-26g)

Installed: `ip-adapter-faceid-plusv2_sdxl.bin` (`ComfyUI-Shared/models/ipadapter/`),
`ip-adapter-faceid-plusv2_sdxl_lora.safetensors` (`…/loras/`), InsightFace `buffalo_l`
(`ComfyUI/models/insightface/models/buffalo_l/`), and `insightface` 2.0 + `onnx`
1.23.0 + `ml_dtypes` 0.6.0 in the ComfyUI venv (all hash-verified; **non-commercial
research licence** for the FaceID weights and InsightFace models). InsightFace runs
on CPU (onnxruntime here is CPU-only), and only for the reference image.

Identity score = ArcFace (buffalo_l w600k_r50) cosine between the reference face and
the man's face in each of 24 frames (all detected). **Caveat:** this is the embedding
family FaceID is conditioned on, so it is not an independent judge, and every value is
below usual same-person thresholds because the face is ~60 px.

| configuration | mean | f1–12 | f13–24 | min | look |
|---|---|---|---|---|---|
| PLUS FACE, full-body reference (§6d) | −0.017 | 0.025 | −0.059 | −0.148 | drifts to another person |
| PLUS FACE, face crop + mask (§6e) | 0.029 | 0.044 | 0.015 | −0.058 | natural, consistent, not Kent by ArcFace |
| + PLUS FACE detail 0.5 (§6f) | 0.040 | 0.043 | 0.036 | −0.059 | as above, older late face |
| FaceID main (w 0.8, LoRA 0.6) + FaceID detail | **0.219** | 0.200 | 0.237 | 0.148 | receding hairline right; head oversized, long hair from f14, caricature at f24, scene restyled |
| FaceID main (w 0.6, LoRA 0.4) + FaceID detail | 0.121 | 0.069 | 0.173 | 0.009 | same problems, milder |
| **PLUS FACE main + FaceID only in the detail pass** | **0.173** | 0.178 | 0.169 | 0.071 | body, hair and scene unchanged (main pass pixel-identical to §6f); rounder face, receding hairline; slight cartoonish eyes f14–20 |

Recommended configuration for this approach: PLUS FACE on the main pass (face crop +
character mask), FaceID Plus V2 only inside the video face-detail pass (denoise 0.5).
Flicker in the head region: 8.88 vs 8.74 undetailed. Likeness acceptance is the
operator's.

## 7. What a real `render_video_from_reference` still needs (not built)

1. An operator decision on §3c: approve the ~17 GB Wan 2.2 Animate download
   (recommended for this need), or the ~1.2 GB VACE 1.3B module (cheapest real
   v2v), or accept the installed AnimateDiff-SDXL quality with no download.
2. A pinned API template per approach (graph JSON under
   `local_agent/runtime/gvd_tool_router/…` with its sha256), built from the
   node classes listed in §3a; DWPose/depth extraction from §6 is its first
   stage.
3. A measured local VRAM profile (peak MiB at the chosen window size) — the GVD
   registry refuses to activate any implementation without one.
4. A background job runner with the existing patterns: `preflight_execute`
   (owner file, port 8188, thermal guard), one owned backend per job,
   `story_image_job_status`-style polling, a manifest with `verified_outputs`
   (sha256, ffprobe of the stitched mp4, frame count vs plan), and never a
   success claim without that evidence. For a 70 s clip this means 15–47
   windows stitched in order; window overlap/blending is part of the template.
5. A visual check of the result against the reference and the character
   still, frame-level, by a human — the judge in `gvd_qa` can rank, not pass.

## 8. How to ask for it in chat

- "Plan a motion transfer from `<video>` with `<image>` as the character" →
  the model calls `plan_video_from_reference` and reports feasibility and
  the download decision. Nothing renders.
- After approving a download and placing the file in the folder named in
  §3c, the same call flips that approach to `feasible_now: true`; it is still
  not renderable until §7 items 2–4 exist.
