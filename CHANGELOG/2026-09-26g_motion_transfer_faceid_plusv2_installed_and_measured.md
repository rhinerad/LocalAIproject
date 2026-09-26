# 2026-09-26g — Motion transfer: IP-Adapter FaceID Plus V2 (SDXL) downloaded and installed with operator approval (five items, all hash-verified); FaceID used only inside the video face-detail pass is the best balance (ArcFace identity 0.173 vs 0.040, body/scene unchanged); FaceID on the main pass scores highest but enlarges the head and caricatures the face

Continues `2026-09-26a`. Id claimed once with `scripts/next_changelog_id.py`
(other sessions took `26b`–`26f` meanwhile). Benign inputs only (Equal Shares
`02A` clip, Kent reference copies in the owned input dir).

## Approval (chat, this session)

Operator chose "faceid". I listed the exact five items (files, sources, sizes,
destinations, the non-commercial licence, the insightface-2.0 risk, the content
rule) and asked. Operator: "yes, go ahead with all five".

## 1. Downloads (`local_agent/runtime/motion_transfer_20260925/faceid_download.py`; manifest `faceid_download_manifest.json`)

Streamed to `<dest>.part` with sha256 computed on the fly, renamed only on
exact size + hash match; never overwrites.

| item | source (host served) | bytes | sha256 (= published) | destination |
|---|---|---|---|---|
| `ip-adapter-faceid-plusv2_sdxl.bin` | huggingface.co/h94/IP-Adapter-FaceID (us.aws.cdn.hf.co) | 1 487 555 181 | `c6945d82b543700cc3ccbb98d363b837e9c596281607857c74b713a876daf5fb` (HF LFS oid) | `A:\Users\rhine\ComfyUI-Shared\models\ipadapter\` |
| `ip-adapter-faceid-plusv2_sdxl_lora.safetensors` | same | 371 842 896 | `f24b4bb2dad6638a09c00f151cde84991baf374409385bcbab53c1871a30cb7b` (HF LFS oid) | `A:\Users\rhine\ComfyUI-Shared\models\loras\` |
| `buffalo_l.zip` | github.com/deepinsight/insightface release `model-zoo` (release-assets.githubusercontent.com) | 288 621 354 | `80ffe37d8a5940d59a7384c201a2a38d4741f2f3c51eef46ebb28218a7b0ca2f` (GitHub asset digest) | `…\Rockernow\ComfyUI\models\insightface\models\` |

`buffalo_l.zip` extracted (`faceid_extract_buffalo.py`, flat zip, CRC-checked,
zip kept) to `…\models\insightface\models\buffalo_l\`: `genderage.onnx`,
`2d106det.onnx`, `det_10g.onnx`, `1k3d68.onnx`, `w600k_r50.onnx` (sha256s in
`faceid_extract_buffalo.log`). That folder is where
`comfyui_ipadapter_plus/utils.py insightface_loader` looks
(`folder_paths.models_dir/insightface`).

## 2. Python packages (ComfyUI `.venv`, Python 3.13.12)

`pip install --no-deps --only-binary :all: insightface==2.0 onnx==1.23.0
ml_dtypes==0.6.0` → exit 0 (`pip_install_26b.log`). `pip freeze` before/after
(`pip_freeze_before_26b.txt`, `pip_freeze_after_26b.txt`): **exactly three
lines added, nothing else changed**. insightface 2.0 is a pure-Python wheel
(1 124 511 B); onnx `cp312-abi3` wheel (7 872 197 B); ml_dtypes wheel 439 kB
(I had quoted ~136 KB from a PyPI read; the actual wheel was 439 kB).
`pip check` reports three **pre-existing, unrelated** conflicts (gpytoolbox vs
numpy/scipy, open-clip-torch vs timm), with none of those packages changed.
`onnxruntime` 1.27.0 was already present (CPU provider only), so InsightFace
runs on CPU.

Reversal if ever needed: `pip uninstall insightface onnx ml_dtypes` in that
venv; the downloaded files are standalone.

## 3. Compatibility test (CPU, no GPU, no download) — `faceid_import_test.py` / `.log`

insightface 2.0 with exactly the calls the IP-Adapter pack makes:
`FaceAnalysis(name="buffalo_l", root=…, providers=[CPU])`, `prepare(ctx_id=0,
det_size=(640,640))`, `det_model.input_size` assignable, `get()`, `kps`,
`normed_embedding` (512-d, norm 1.0), `face_align.norm_crop(…, 256)`. One face
found in the face crop (det 0.812) and in the full-body master (det 0.878).
**No files added under the insightface root** (no auto-download).

## 4. Runner (`animatediff_v2v_poc.py`, CRLF kept)

`_edit_runner_26b_faceid.py`: `--faceid` (node 13 →
`IPAdapterUnifiedLoaderFaceID` "FACEID PLUS V2", provider CPU; nodes 15 and 43
→ `IPAdapterFaceID` with `weight_faceidv2`), `--fid-lora`, `--fid-v2`.
`_edit_runner_26b_fid_detail.py`: `--faceid-detail-only` (PLUS FACE stays on
nodes 13/15; new node 50 = FaceID loader on the AnimateDiff model feeding node
43 only, so the FaceID LoRA touches only the face crop). Both are exact
anchors, refuse a second run, and record the settings in the manifest.

## 5. Runs (owned backend; operator chat idle and chat model unloaded before each; preflight owner + port + thermal; released after each)

All: 24 frames, face crop + left-region mask on the main adapter, DWPose face
off + xinsir sticks, face-detail pass at 0.50, seed 20260925, 768×448. Each:
history `success`, 96 files with sha256.

| tag | adapters | prompt_id | backend start | render | peak MiB | detailed mp4 sha256 |
|---|---|---|---|---|---|---|
| `pass22_faceid_fd050` | FaceID main + detail (w 0.8, LoRA 0.6, v2 1.0) | `2c8bc844-b575-428d-bdfe-21a2154e265d` | 777.0 s | 630.2 s | 14 691 | `798244dc0380d030108ab7ab1113642ea95149f7f759b01c3b1c1b3634bd4f41` |
| `pass23_faceid_w06_l04_fd050` | same, w 0.6, LoRA 0.4 | `b86b2633-64a0-41dc-aa80-81ea4a49ba6a` | 803.9 s | 718.5 s | 14 711 | `9c26d88628159ca92328457dacd37faf2a9ed0f4f63785b0b5c70ead7395e8b7` |
| `pass24_pf_main_faceid_detail_fd050` | PLUS FACE main, FaceID (w 0.8, LoRA 0.6) detail only | `d9643d78-d67b-4f21-a79b-99b98d43fdfa` | 227.4 s | 540.2 s | 14 654 | `deb41114f355c431d57676cffa9921f0a13b1fd86b8f7f550574417782fd4581` |

`pass24`'s undetailed frames are pixel-identical to `pass21b` (24/24), so its
difference from `pass21b` is only the detailer's adapter. Backend cold starts
of 777–804 s are within the 900 s limit set in 25t.

## 6. Identity score (`identity_score.py`, CPU; `identity_scores_26b.json`, `identity_score_26b.log`)

ArcFace (buffalo_l `w600k_r50`) cosine similarity between the reference face
(full-body master, det 0.878) and the man's face (leftmost face, x < 420) in
each of 24 frames; all 24 detected in every run.

| configuration | mean | f1–12 | f13–24 | min |
|---|---|---|---|---|
| p15 PLUS FACE, full-body reference | −0.017 | 0.025 | −0.059 | −0.148 |
| p18 PLUS FACE, face crop + mask | 0.029 | 0.044 | 0.015 | −0.058 |
| p21b + PLUS FACE detail 0.5 | 0.040 | 0.043 | 0.036 | −0.059 |
| p22 FaceID main, undetailed | 0.151 | 0.100 | 0.202 | 0.050 |
| p22 FaceID main + FaceID detail | **0.219** | 0.200 | 0.237 | 0.148 |
| p23 FaceID weaker, undetailed | 0.091 | 0.058 | 0.124 | 0.021 |
| p23 FaceID weaker + FaceID detail | 0.121 | 0.069 | 0.173 | 0.009 |
| p24 PLUS FACE main + FaceID detail | **0.173** | 0.178 | 0.169 | 0.071 |

**Caveats:** this is the embedding family FaceID is conditioned on, so it is
not an independent judge. All values are below usual same-person thresholds
because the face is ~60 px. The PLUS FACE runs looked consistent but score
near zero on this metric.

## 7. Visual check (native-resolution head crops: `id_26b_plusface_vs_faceid.png`, `id_26b_faceid_tuning.png`, `id_26b_detail_plusface_vs_faceid.png`; full frames `id_26b_full_frames.png`; `fd_eval_pass22/23/24*.png`)

- p22 (FaceID everywhere): receding hairline and high forehead like the
  reference; the brown bleed is gone. But the head is **oversized for the
  body**, hair grows long from frame 14, frame 24 is a caricature, and the
  whole scene is restyled (the FaceID LoRA acts on the whole model).
  Upright, motion follows, woman fine. Head-region flicker 8.05 vs 7.95
  undetailed.
- p23 (weaker): the same problems, milder. Strength is not the cause.
- **p24 (FaceID in the detail pass only):** body, hair, room and woman
  unchanged. Faces rounder with the receding hairline, closer to the
  reference; slight cartoonish eyes at frames 14–20. Head-region flicker 8.88
  vs 8.74.
- My frame-level judgement plus the metric; likeness acceptance is the
  operator's.

## 8. Text updated (`_edit_26g_text.py`: every anchor verified, and the file's mtime re-checked immediately before each write)

`local_agent/motion_transfer.py` (LF) AnimateDiff `why`;
`gvd_tool_router/catalog_seed.py` (LF) AnimateDiff seed reason only (another
session edited other rows of this file at 01:15 for `26b`; untouched); doc
§6g; `TODO.md` note. `python -m unittest test_motion_transfer_plan
test_gvd_tool_router test_queued_analysis_honesty`: **89 OK**
(`tests_26g.log`), including the other session's router changes.

## Not done / next

- Recommended configuration for a template: PLUS FACE main pass (face crop +
  character mask) + FaceID Plus V2 only in the video face-detail pass (0.5).
  Still needs: per-frame character selection instead of "leftmost face" and
  the static mask, a pinned template, a GVD VRAM profile, and promotion. The
  `render_video_from_reference` tool is not built.
- The planner's weight inventory does not list the FaceID files (they are
  optional to this approach); text only.
- Content rule unchanged: never put a real, identifiable person's likeness
  into sexual content with these tools; FaceID makes a transferred face more
  faithful.
