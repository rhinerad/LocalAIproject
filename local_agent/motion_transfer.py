#!/usr/bin/env python3
"""Reference-video motion transfer with character replacement — planning only.

The operator asked (2026-09-25, chat 1f0e3e61bdb0487a) for a reference
video's motion reused over its whole length with a different character, from a
still, performing it. No render path in this tree does that: every video path
(render_story_image → FLF2V, the prompt-pack pipeline, comfy_generate) takes
still frames, not a reference clip's motion. This module answers, without
rendering, starting ComfyUI, loading a model, or downloading anything, which
of three ComfyUI approaches this install can run now and exactly what each
missing one needs. See docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md.

Presence checks use the same resolver as the still renderer
(work/image_render.model_file_on_configured_paths over
work/runtime/image_render_model_paths.yaml) plus the ComfyUI checkout's
custom_nodes/ tree, so "installed" here means "visible to the ComfyUI this
project renders with", not "some file exists somewhere".
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
if str(ROOT / "work") not in sys.path:
    sys.path.insert(0, str(ROOT / "work"))

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# DWPose weights controlnet_aux resolves offline (its node defaults), relative
# to custom_nodes/comfyui_controlnet_aux/ckpts/.
DWPOSE_CKPTS = (
    "yzd-v/DWPose/yolox_l.onnx",
    "hr16/DWPose-TorchScript-BatchSize5/dw-ll_ucoco_384_bs5.torchscript.pt",
)
DEPTH_CKPTS = ("depth-anything/Depth-Anything-V2-Large/depth_anything_v2_vitl.pth",)


class PlanError(ValueError):
    pass


def _w(folder: str, names: tuple[str, ...], approx_gb: float, *, purpose: str,
       download: str = "", optional: bool = False) -> dict[str, Any]:
    return {"folder": folder, "names": list(names), "approx_gb": approx_gb,
            "purpose": purpose, "download": download, "optional": optional}


# Three ways to do it. Order = preference when feasible. Sizes are the
# published file sizes of the named repackagings, rounded; they are what an
# operator would have to approve downloading, not measurements from this
# machine (which does not have them).
APPROACHES: list[dict[str, Any]] = [
    {
        "id": "wan22_animate_14b",
        "label": "Wan 2.2 Animate 14B — character animation / replacement from a reference video",
        "why": ("Purpose-built for this request: drives a character still with a reference "
                "clip's body pose (DWPose) and face motion, in 'animation' mode (new clip) or "
                "'replacement' mode (the reference clip with the character swapped in, relit)."),
        "nodes": ("ComfyUI-WanVideoWrapper", "comfyui_controlnet_aux", "ComfyUI-VideoHelperSuite"),
        "node_classes": ("WanVideoAnimateEmbeds", "DWPreprocessor", "VHS_LoadVideoPath", "VHS_VideoCombine"),
        "optional_nodes": ("ComfyUI-segment-anything-2",),
        "aux_ckpts": DWPOSE_CKPTS,
        "weights": [
            _w("diffusion_models",
               ("Wan2_2-Animate-14B_fp8_e4m3fn_scaled_KJ.safetensors",
                "Wan2_2-Animate-14B_fp8_e5m2_scaled_KJ.safetensors",
                "Wan2.2-Animate-14B_fp8_e4m3fn.safetensors",
                "Wan2_2-Animate-14B_bf16.safetensors"),
               17.0, purpose="the Animate diffusion model (fp8 scaled)",
               download="https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled (Wan22Animate/)"),
            _w("loras",
               ("Wan22_relight_lora_fp16.safetensors",
                "Wan2.2-Animate-14B-relight-lora_fp16.safetensors"),
               0.6, purpose="replacement-mode relighting LoRA", optional=True,
               download="https://huggingface.co/Kijai/WanVideo_comfy (Wan22Animate/)"),
            _w("text_encoders",
               ("umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5-xxl-enc-fp8_e4m3fn.safetensors",
                "umt5_xxl_fp16.safetensors", "umt5-xxl-encoder-Q8_0.gguf"),
               6.4, purpose="umt5-xxl text encoder"),
            _w("vae", ("wan_2.1_vae.safetensors", "Wan2_1_VAE_bf16.safetensors",
                       "Wan2_1_VAE_fp32.safetensors"),
               0.25, purpose="Wan 2.1 VAE"),
            _w("clip_vision", ("clip_vision_h.safetensors",), 1.2, purpose="CLIP vision H"),
        ],
        "frame_plan": {"target_fps": 16, "window_frames": 81, "overlap_frames": 5,
                       "suggested_size": "832x480 (16 GB card; block swap on)"},
        "vram_note": ("14B fp8 with WanVideoWrapper block swap has run on this 16 GB RTX 5080 "
                      "for Wan 2.2 I2V; Animate adds pose/face embeds per window. Unmeasured "
                      "here — a local VRAM profile is required before promotion."),
    },
    {
        "id": "wan21_vace_1_3b",
        "label": "Wan 2.1 VACE 1.3B — control video (pose/depth) + reference image",
        "why": ("Smallest download that gives a real pose-driven video-to-video path with a "
                "reference image for identity. Lower fidelity than 14B; fits 16 GB easily."),
        "nodes": ("ComfyUI-WanVideoWrapper", "comfyui_controlnet_aux", "ComfyUI-VideoHelperSuite"),
        "node_classes": ("WanVideoVACEEncode", "WanVideoVACEModelSelect", "DWPreprocessor",
                         "VHS_LoadVideoPath", "VHS_VideoCombine"),
        "optional_nodes": (),
        "aux_ckpts": DWPOSE_CKPTS,
        "weights": [
            _w("diffusion_models",
               ("Wan2_1-VACE_module_1_3B_bf16.safetensors",
                "wan2.1_vace_1.3B_fp16.safetensors",
                "Wan2.1-VACE-1.3B_fp16.safetensors"),
               1.2, purpose="VACE 1.3B module (~1.2 GB, pairs with the base below) or the "
                            "full VACE 1.3B model (~6.7 GB, Comfy-Org repackaged)",
               download="https://huggingface.co/Kijai/WanVideo_comfy (VACE/) or "
                        "https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged"),
            _w("diffusion_models", ("wan2.1_t2v_1.3B_fp16.safetensors",), 2.7,
               purpose="base Wan 2.1 T2V 1.3B the VACE module attaches to"),
            _w("text_encoders",
               ("umt5_xxl_fp8_e4m3fn_scaled.safetensors", "umt5-xxl-enc-fp8_e4m3fn.safetensors",
                "umt5_xxl_fp16.safetensors", "umt5-xxl-encoder-Q8_0.gguf"),
               6.4, purpose="umt5-xxl text encoder"),
            _w("vae", ("wan_2.1_vae.safetensors", "Wan2_1_VAE_bf16.safetensors",
                       "Wan2_1_VAE_fp32.safetensors"),
               0.25, purpose="Wan 2.1 VAE"),
        ],
        "frame_plan": {"target_fps": 16, "window_frames": 81, "overlap_frames": 5,
                       "suggested_size": "832x480"},
        "vram_note": "1.3B fits 16 GB with room to spare; unmeasured here.",
    },
    {
        "id": "animatediff_sdxl_pose_ipadapter",
        "label": "AnimateDiff SDXL + ControlNet union (openpose/depth) + IP-Adapter Plus Face",
        "why": ("Every weight is already installed and a single 16-frame context window "
                "rendered live on 2026-09-25. Lowest quality of the three (SDXL motion "
                "modules flicker; identity from a face IP-Adapter, not full body). Any clip "
                "longer than one context window needs AnimateDiff-Evolved's sliding window, "
                "which refused core ControlNets until the ComfyUI-Advanced-ControlNet pack "
                "was installed with operator approval (v1.6.0, CHANGELOG 2026-09-25u); "
                "24-frame, two-window clips now render. The "
                "vertically inverted output of 2026-09-25s is root-caused (CHANGELOG "
                "2026-09-25t): it appeared only when DWPose drew face and hand keypoints "
                "together (xinsir's union model was trained on body-only poses); with "
                "DWPreprocessor detect_face=disable a 16-frame window rendered upright and "
                "followed the reference motion, so a template must disable face keypoints. "
                "Identity needs a tight, square face crop of the character still: with "
                "the full-body master the character drifted into a different person; "
                "with a face crop (plus an IP-Adapter attention mask over the "
                "character's region to stop colour bleed) it held through a 24-frame "
                "clip, softening near the end (CHANGELOG 2026-09-25v). An Impact Pack video "
                "face-detail pass (DetailerForEachPipeForAnimateDiff, denoise 0.5) pulls the "
                "late frames toward the reference without adding flicker, but faces stay "
                "soft: at 768x448 a face is ~60 px (CHANGELOG 2026-09-26a). IP-Adapter "
                "FaceID Plus V2 SDXL is installed (operator-approved, non-commercial "
                "licence); used only inside the face-detail pass it raises ArcFace "
                "similarity to the reference ~4x without changing body, hair or scene; "
                "used on the main pass it scores highest but enlarges the head and "
                "caricatures the face (CHANGELOG 2026-09-26g)."),
        "nodes": ("ComfyUI-AnimateDiff-Evolved", "comfyui_controlnet_aux",
                  "comfyui_ipadapter_plus", "ComfyUI-VideoHelperSuite",
                  "ComfyUI-Advanced-ControlNet"),
        "node_classes": ("ADE_AnimateDiffLoaderGen1", "ADE_StandardUniformContextOptions",
                         "DWPreprocessor", "SetUnionControlNetType", "ControlNetApplyAdvanced",
                         "ACN_AdvancedControlNetApply_v2", "IPAdapterUnifiedLoader", "IPAdapterAdvanced",
                         "VHS_LoadVideoPath", "VHS_VideoCombine"),
        "optional_nodes": (),
        "aux_ckpts": DWPOSE_CKPTS,
        "weights": [
            _w("checkpoints",
               ("sd_xl_base_1.0_0.9vae.safetensors", "RealVisXL_V5.0_fp16.safetensors",
                "dreamshaperXL_lightningDPMSDE.safetensors", "realismIllustriousBy_v55FP16.safetensors"),
               6.6, purpose="any SDXL checkpoint"),
            _w("animatediff_models", ("mm_sdxl_v10_beta.ckpt", "hsxl_temporal_layers.safetensors"),
               0.9, purpose="SDXL motion module"),
            _w("controlnet", ("controlnet-union-sdxl-1.0-promax.safetensors",), 2.4,
               purpose="SDXL union ControlNet (openpose + depth types)"),
            _w("ipadapter", ("ip-adapter-plus-face_sdxl_vit-h.safetensors",), 0.8,
               purpose="IP-Adapter Plus Face SDXL (identity)"),
            _w("clip_vision", ("CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",), 1.2,
               purpose="CLIP ViT-H for the IP-Adapter"),
        ],
        "frame_plan": {"target_fps": 8, "window_frames": 16, "overlap_frames": 4,
                       "suggested_size": "768x448"},
        "vram_note": ("Measured on this 16 GB RTX 5080 (CHANGELOG 2026-09-25s/u): SDXL + "
                      "motion module + union ControlNet + IP-Adapter, 16-frame context at "
                      "768x448 peaks 14.6-15.9 GB of 16.3 GB; 1024x576 is unmeasured and "
                      "unlikely to fit."),
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _default_custom_nodes() -> Path:
    import mcp_client
    return Path(mcp_client.COMFYUI_CODE_PATH) / "custom_nodes"


def _node_installed(custom_nodes: Path, name: str) -> bool:
    return (custom_nodes / name).is_dir()


def _weight_hit(weight: dict[str, Any], config_path: Path | None) -> str | None:
    import image_render
    for name in weight["names"]:
        try:
            hit = image_render.model_file_on_configured_paths(
                name, weight["folder"], config_path=config_path)
        except image_render.ImageRenderError:
            return None
        if hit is not None:
            return str(hit)
    return None


def inventory(*, custom_nodes: Path | None = None,
              config_path: Path | None = None) -> list[dict[str, Any]]:
    """Per-approach presence report. Filesystem only; never starts ComfyUI."""
    nodes_dir = custom_nodes or _default_custom_nodes()
    aux_root = nodes_dir / "comfyui_controlnet_aux" / "ckpts"
    out: list[dict[str, Any]] = []
    for approach in APPROACHES:
        installed: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for name in approach["nodes"]:
            row = {"kind": "custom_node", "name": name}
            (installed if _node_installed(nodes_dir, name) else missing).append(row)
        for rel in approach["aux_ckpts"]:
            row = {"kind": "preprocessor_weight", "name": rel,
                   "download": "auto-fetched by comfyui_controlnet_aux on first use"}
            (installed if (aux_root / rel).is_file() else missing).append(row)
        for weight in approach["weights"]:
            hit = _weight_hit(weight, config_path)
            row = {"kind": "model_weight", "folder": weight["folder"],
                   "purpose": weight["purpose"], "optional": weight["optional"]}
            if hit:
                row["path"] = hit
                installed.append(row)
            else:
                row.update({"accepted_names": weight["names"],
                            "approx_gb": weight["approx_gb"],
                            "download": weight["download"]})
                missing.append(row)
        required_missing = [m for m in missing if not m.get("optional")]
        download_gb = round(sum(float(m.get("approx_gb") or 0) for m in required_missing), 1)
        out.append({
            "id": approach["id"],
            "label": approach["label"],
            "why": approach["why"],
            "feasible_now": not required_missing,
            "installed": installed,
            "missing": missing,
            "download_gb_to_enable": download_gb,
            "optional_nodes": [
                {"name": n, "installed": _node_installed(nodes_dir, n)}
                for n in approach["optional_nodes"]],
            "node_classes": list(approach["node_classes"]),
            "frame_plan_defaults": dict(approach["frame_plan"]),
            "vram_note": approach["vram_note"],
        })
    return out


def probe_video(path: str | Path) -> dict[str, Any]:
    """ffprobe summary of the reference clip (duration, fps, size, sha256)."""
    import media_tools
    p = Path(path)
    info = media_tools._probe(p)
    fmt = info.get("format") or {}
    streams = [s for s in info.get("streams") or [] if s.get("codec_type") == "video"]
    if not streams:
        raise PlanError(f"no video stream in {p}")
    v = streams[0]
    num, _, den = str(v.get("r_frame_rate") or "0/1").partition("/")
    try:
        fps = float(num) / float(den or 1)
    except (TypeError, ValueError, ZeroDivisionError):
        fps = 0.0
    duration = float(fmt.get("duration") or 0)
    return {
        "path": str(p), "duration_s": round(duration, 3), "fps": round(fps, 3),
        "width": int(v.get("width") or 0), "height": int(v.get("height") or 0),
        "source_frames": int(round(duration * fps)) if fps else None,
        "size_bytes": int(fmt.get("size") or p.stat().st_size),
        "sha256": _sha256(p),
        "audio_streams": sum(1 for s in info.get("streams") or [] if s.get("codec_type") == "audio"),
    }


def probe_image(path: str | Path) -> dict[str, Any]:
    from PIL import Image
    p = Path(path)
    with Image.open(p) as im:
        width, height = im.size
    return {"path": str(p), "width": width, "height": height,
            "size_bytes": p.stat().st_size, "sha256": _sha256(p)}


def frame_plan(duration_s: float, defaults: dict[str, Any],
               target_fps: float | None = None) -> dict[str, Any]:
    fps = float(target_fps or defaults["target_fps"])
    frames = max(1, int(math.ceil(duration_s * fps)))
    window = int(defaults["window_frames"])
    overlap = int(defaults.get("overlap_frames") or 0)
    stride = max(1, window - overlap)
    segments = 1 if frames <= window else 1 + int(math.ceil((frames - window) / stride))
    return {"target_fps": fps, "output_frames": frames, "window_frames": window,
            "overlap_frames": overlap, "windows": segments,
            "suggested_size": defaults.get("suggested_size"),
            "note": ("Whole reference length at target_fps; long clips render as overlapping "
                     "windows stitched in order. Time per window is unmeasured on this machine.")}


def _validated_path(value: object, allowed: set[str], label: str) -> Path:
    raw = str(value or "").strip()
    if not raw:
        raise PlanError(f"{label} is required")
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = ROOT / p
    p = p.resolve()
    if not p.is_file():
        raise PlanError(f"{label} not found: {p}")
    if p.suffix.lower() not in allowed:
        raise PlanError(f"{label} has unsupported type {p.suffix!r}")
    return p


def gvd_manifest(video: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    """ShotManifest dict for gvd_route_shot: identity mode + motion reference."""
    return {
        "shot_id": "MT01",
        "script_intent": ("Reproduce the reference video's motion for its whole length with "
                          "the supplied character performing it."),
        "camera_motion": "as in the reference video",
        "continuity_mode": "identity",
        "character_state": [{
            "character_id": "reference_character", "revision": "v1",
            "face_refs": [{"asset_id": Path(image["path"]).name, "sha256": image["sha256"],
                           "media_type": "image/png"}],
            "wardrobe_refs": [], "wardrobe_description": "as in the character still",
            "props": [], "screen_position": "as in the reference video",
            "pose": "driven by the reference video", "expression": "driven by the reference video",
        }],
        "duration_s": float(video["duration_s"]),
        "width": int(video["width"] or 832), "height": int(video["height"] or 480),
        "fps_num": 24, "fps_den": 1,
        "hard_requirements": [],
        "priorities": {},
        "motion_reference_video": {"asset_id": Path(video["path"]).name,
                                   "sha256": video["sha256"], "media_type": "video/mp4"},
    }


def plan(reference_video: object, character_image: object, *,
         target_fps: float | None = None, custom_nodes: Path | None = None,
         config_path: Path | None = None, gvd_layout=None) -> dict[str, Any]:
    """The whole read-only answer. Raises PlanError for bad inputs."""
    vpath = _validated_path(reference_video, VIDEO_EXTS, "reference_video")
    ipath = _validated_path(character_image, IMAGE_EXTS, "character_image")
    video = probe_video(vpath)
    image = probe_image(ipath)
    approaches = inventory(custom_nodes=custom_nodes, config_path=config_path)
    for row in approaches:
        row["frame_plan"] = frame_plan(video["duration_s"], row["frame_plan_defaults"], target_fps)
    feasible = [row for row in approaches if row["feasible_now"]]
    recommended_now = feasible[0]["id"] if feasible else None
    best_with_download = approaches[0]["id"]
    decisions: list[str] = []
    for row in approaches:
        if not row["feasible_now"]:
            names = ", ".join(f"{m['folder']}/{m['accepted_names'][0]} (~{m['approx_gb']} GB)"
                              for m in row["missing"]
                              if m["kind"] == "model_weight" and not m.get("optional"))
            nodes = ", ".join(m["name"] for m in row["missing"] if m["kind"] != "model_weight")
            what = "; ".join(x for x in (names, f"nodes: {nodes}" if nodes else "") if x)
            decisions.append(f"{row['id']}: approve downloading {what} "
                             f"(~{row['download_gb_to_enable']} GB total)")
    gvd_route: dict[str, Any] | None = None
    try:
        from gvd_tool_router.service import route_shot
        decision = route_shot(gvd_manifest(video, image), gvd_layout)
        gvd_route = {k: decision.get(k) for k in (
            "status", "tool_name", "reason_codes", "missing_capabilities")}
        gvd_route["blocked_candidates"] = [
            {"implementation_id": c["implementation_id"], "status": c["status"],
             "disabled_reason": c["disabled_reason"]}
            for c in decision.get("blocked_candidates") or []]
    except Exception as exc:  # the plan is still useful without the router
        gvd_route = {"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"}
    return {
        "planned": True,
        "rendered": False,
        "reference_video": video,
        "character_image": image,
        "approaches": approaches,
        "recommended_now": recommended_now,
        "best_with_download": best_with_download,
        "operator_decisions_needed": decisions,
        "gvd_route": gvd_route,
        "note": ("Planning only: nothing was rendered, generated, downloaded, or started, "
                 "and no model was loaded. A feasible_now approach still needs a pinned "
                 "ComfyUI API template, a measured local VRAM profile and a verified "
                 "render before it can be offered as a tool."),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("reference_video")
    ap.add_argument("character_image")
    ap.add_argument("--target-fps", type=float, default=None)
    args = ap.parse_args(argv)
    try:
        print(json.dumps(plan(args.reference_video, args.character_image,
                              target_fps=args.target_fps), indent=2, ensure_ascii=False))
    except PlanError as exc:
        print(f"ERROR: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
