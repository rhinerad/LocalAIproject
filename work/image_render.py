#!/usr/bin/env python3
"""Guarded general still-image graph planner for the local storyboard system.

``--plan`` is deliberately read-only: it queries ComfyUI's live node catalogue,
validates the graph it would submit, and prints JSON.  It never loads a model.
Actual execution is intentionally not implicit: it requires ``--execute`` and
``--allow-model-load`` and refuses an existing ComfyUI backend or render owner.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import uuid
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import thermal_guard
sys.path.insert(0, str(ROOT / "local_agent"))
from production_integrity import process_lock

API = "http://127.0.0.1:8188"
STORY_ROOT = ROOT / "outputs" / "stories"
OWNER = ROOT / "outputs" / "equal_shares" / "runtime" / "render_queue_owner.json"
IMAGE_OWNER = ROOT / "work" / "runtime" / "image_render_owner.json"
MODEL_PATHS = ROOT / "work" / "runtime" / "image_render_model_paths.yaml"
IMAGE_RUNTIME = ROOT / "work" / "runtime" / "image_render_runtime"
IMAGE_INPUT = IMAGE_RUNTIME / "input"
IMAGE_USER = IMAGE_RUNTIME / "user"
IMAGE_TEMP = IMAGE_RUNTIME / "temp"
IMAGE_OUTPUT = STORY_ROOT / "_comfy_output"
COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
DEFAULT_MODEL = "RealVisXL_V5.0_fp16.safetensors"
REALPRO_FLUX_UNET = "realProV3_realProV3Unet.safetensors"
# 2026-10-04 (operator 10-03: every generated image the Backrooms way): the Backrooms stills' checkpoint and settings,
# read from the prompt embedded in ComfyUI-Shared/output/astra_backrooms_stills/C031_last_00001_.png (CHANGELOG
# 2026-09-18k).
BACKROOMS_FLUX_CHECKPOINT = "flux1-dev-fp8.safetensors"
ALICEMIX_SD15_CHECKPOINT = "realAlicemixV1_v10.safetensors"
REALISTICVISION_SD15_CHECKPOINT = "realisticVisionV60B1_v51HyperVAE.safetensors"
HAND_REFINER_CONTROLNET = "control_sd15_inpaint_depth_hand_fp16.safetensors"
ALICEMIX_POSITIVE_PREFIX = "(extremely intricate, detailed light, detailed shadow:1.1), (F4, 1/800s, ISO 100, RAW)"
ALICEMIX_NEGATIVE_SUFFIX = "(low quality, worst quality, extra fingers, deformed hands, polydactyl:1.5), (monochrome, grayscale:1.5)"
MODEL_PROFILES = {
    "realvisxl": {"family": "sdxl", "model": DEFAULT_MODEL,
                   "defaults": {"width": 1024, "height": 1024, "steps": 35, "cfg": 6.0, "sampler": "dpmpp_2m_sde", "scheduler": "karras"}},
    "backrooms_flux": {"family": "flux", "model": BACKROOMS_FLUX_CHECKPOINT,
                       "defaults": {"width": 1504, "height": 832, "steps": 12, "cfg": 1.0, "sampler": "euler",
                                    "scheduler": "simple"}},
    "realpro_flux": {"family": "flux", "model": REALPRO_FLUX_UNET,
                      "defaults": {"width": 896, "height": 1152, "steps": 28, "cfg": 1.0, "sampler": "euler", "scheduler": "simple"}},
    "alicemix_sd15": {"family": "sd15", "model": ALICEMIX_SD15_CHECKPOINT,
                        "defaults": {"width": 768, "height": 1024, "steps": 30, "cfg": 11.0, "sampler": "dpmpp_2m", "scheduler": "karras"}},
    "realisticvision_sd15": {
        "family": "sd15", "model": REALISTICVISION_SD15_CHECKPOINT,
        "defaults": {"width": 768, "height": 768, "steps": 30, "cfg": 7.0,
                     "sampler": "dpmpp_2m_sde", "scheduler": "karras"},
    },
}


def profile_defaults(profile: str) -> dict:
    """Return a copy so call sites cannot mutate the registered profile."""
    try:
        return dict(MODEL_PROFILES[profile]["defaults"])
    except KeyError as exc:
        raise ImageRenderError(f"unknown image model profile: {profile}") from exc

_LEGACY_MODEL_FOLDERS = {"unet": "diffusion_models", "clip": "text_encoders"}


def iter_extra_model_folder_paths(folder_name: str,
                                  config_path: Path | None = None) -> list[Path]:
    """Resolve on-disk search dirs for a Comfy model folder type.

    Mirrors ComfyUI ``utils/extra_config.load_extra_path_config``:
    empty path segments are skipped (so ``diffusion_models: ''`` registers
    nothing), ``base_path`` is joined with each relative segment, and legacy
    keys ``unet`` / ``clip`` map to ``diffusion_models`` / ``text_encoders``.
    """
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - Comfy venv always has PyYAML
        raise ImageRenderError("PyYAML is required to resolve image model paths") from exc
    cfg = config_path or MODEL_PATHS
    if not cfg.is_file():
        raise ImageRenderError(f"image model-path configuration missing: {cfg}")
    raw = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    wanted = _LEGACY_MODEL_FOLDERS.get(folder_name, folder_name)
    found: list[Path] = []
    seen: set[str] = set()
    for _name, conf in raw.items():
        if not isinstance(conf, dict):
            continue
        conf = dict(conf)
        base = conf.pop("base_path", None)
        conf.pop("is_default", None)
        if base:
            base = str(Path(os.path.expandvars(os.path.expanduser(str(base)))))
        for key, value in conf.items():
            mapped = _LEGACY_MODEL_FOLDERS.get(str(key), str(key))
            if mapped != wanted:
                continue
            for segment in str(value or "").split("\n"):
                segment = segment.strip()
                # ComfyUI skips empty segments -- '' never means "use base_path".
                if not segment:
                    continue
                full = Path(base, segment) if base else Path(segment)
                if not full.is_absolute():
                    full = (cfg.parent / full).resolve()
                else:
                    full = full.resolve()
                key_s = str(full).lower()
                if key_s in seen:
                    continue
                seen.add(key_s)
                found.append(full)
    return found


def model_file_on_configured_paths(model: str, folder_name: str,
                                   config_path: Path | None = None) -> Path | None:
    """Return the first configured dir that contains ``model``, else None."""
    requested = Path(model)
    # ComfyUI catalogues nested assets by a relative name such as
    # ``bbox/hand_yolov8s.pt``.  Preserve that safe relative path here; using
    # only Path.name incorrectly looked in ``ultralytics/`` instead of its
    # ``ultralytics/bbox/`` child and rejected an asset that ComfyUI could see.
    if requested.is_absolute() or ".." in requested.parts:
        candidates = (Path(requested.name),)
    else:
        candidates = (requested, Path(requested.name))
    for directory in iter_extra_model_folder_paths(folder_name, config_path=config_path):
        for relative in candidates:
            candidate = directory / relative
            if candidate.is_file():
                return candidate
    return None


def assert_configured_model_visible(model: str, folder_name: str,
                                    config_path: Path | None = None) -> Path:
    """Fail fast when extra_model_paths cannot see ``model`` (before Comfy start)."""
    hit = model_file_on_configured_paths(model, folder_name, config_path=config_path)
    if hit is not None:
        return hit
    dirs = iter_extra_model_folder_paths(folder_name, config_path=config_path)
    shown = ", ".join(str(d) for d in dirs) if dirs else (
        "(no search dirs -- empty path segments in image_render_model_paths.yaml?)"
    )
    raise ImageRenderError(
        f"model not on configured {folder_name} paths: {model}; searched: {shown}"
    )



# Single source of truth for the default negative prompt — tools.py imports
# this rather than hardcoding its own copy. Broadened 2026-09-01 after a real
# operator render came back hazy/washed-out (root cause: a t2i call was given
# denoise=0.55, since fixed by forcing denoise=1.0 for t2i in build_graph
# below). This negative prompt is a second, independent layer against the
# same class of defect plus the usual anatomy/artifact failure modes for
# photorealistic humans on RealVisXL.
DEFAULT_NEGATIVE = (
    "blurry, low quality, hazy, foggy, washed out, overexposed, low contrast, "
    "distorted anatomy, extra fingers, fused fingers, mutated hands, malformed "
    "limbs, poorly drawn face, asymmetrical eyes, cross-eyed, crossed eyes, "
    "walleye, strabismus, misaligned eyes, asymmetrical pupils, lazy eye, "
    "plastic skin, doll skin, airbrushed, oversaturated, cartoon, anime, "
    "3d render, cgi, illustration, painting, watermark, text, signature, "
    "logo, jpeg artifacts, low resolution, out of focus, grainy, noise"
)
DEFAULT_STEPS = 35
# Second-pass ("hi-res fix") settings applied automatically to every t2i
# render — see build_graph(). A single 1024x1024 pass renders two full-body
# figures at a face size SDXL struggles to keep coherent (crossed/misaligned
# eyes are a known symptom at that effective face resolution); resampling the
# first pass's latent at a higher size gives the model far more pixels to
# resolve each face into before the image is finalized.
DEFAULT_HIRES_SCALE = 1.5
DEFAULT_HIRES_DENOISE = 0.5
DEFAULT_HIRES_STEPS = 20
# This is deliberately opt-in rather than part of every still-image job.  The
# regular renderer starts ComfyUI with custom nodes disabled, which keeps its
# failure surface small.  When a composition has small, damaged, or
# misaligned faces, the opt-in FaceDetailer pass detects each face and
# re-samples only that crop at a useful resolution.
FACE_DETAIL_MODEL = "bbox/face_yolov8m.pt"
HAND_DETAIL_MODEL = "bbox/hand_yolov8s.pt"
FACE_DETAIL_POSITIVE = (
    "natural photorealistic face, symmetrical eyes, aligned pupils, detailed irises, "
    "natural skin texture, anatomically correct facial features"
)
FACE_DETAIL_NEGATIVE = (
    "cross-eyed, crossed eyes, strabismus, lazy eye, wall-eyed, misaligned pupils, "
    "asymmetrical eyes, malformed face, deformed face, duplicate face, blurry face"
)
IPADAPTER_SDXL_FACE = "ip-adapter-plus-face_sdxl_vit-h.safetensors"
CLIP_VISION_H = "clip_vision_h.safetensors"
CONTROLNET_UNION_SDXL = "controlnet-union-sdxl-1.0-promax.safetensors"
REQUIRED_T2I = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "EmptyLatentImage": ("width", "height", "batch_size"),
    "KSampler": ("model", "seed", "steps", "cfg", "sampler_name", "scheduler",
                 "positive", "negative", "latent_image", "denoise"),
    "LatentUpscaleBy": ("samples", "scale_by", "upscale_method"),
    "VAEDecode": ("samples", "vae"),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_I2I = {"LoadImage": ("image",), "VAEEncode": ("pixels", "vae")}
REQUIRED_IDENTITY_I2I = {
    "IPAdapterModelLoader": ("ipadapter_file",),
    "CLIPVisionLoader": ("clip_name",),
    "IPAdapterAdvanced": (
        "model", "ipadapter", "image", "weight", "weight_type",
        "combine_embeds", "start_at", "end_at", "embeds_scaling",
    ),
}
REQUIRED_IDENTITY_INPAINT = {
    "LoadImage": ("image",),
    "VAEEncode": ("pixels", "vae"),
    "SetLatentNoiseMask": ("samples", "mask"),
    "IPAdapterModelLoader": ("ipadapter_file",),
    "CLIPVisionLoader": ("clip_name",),
    "IPAdapterAdvanced": (
        "model", "ipadapter", "image", "weight", "weight_type",
        "combine_embeds", "start_at", "end_at", "embeds_scaling",
    ),
    "ImageCompositeMasked": ("destination", "source", "x", "y", "resize_source"),
}
REQUIRED_POSE_CONTROL = {
    "ControlNetLoader": ("control_net_name",),
    "SetUnionControlNetType": ("control_net", "type"),
    "ControlNetApplyAdvanced": (
        "positive", "negative", "control_net", "image", "strength",
        "start_percent", "end_percent",
    ),
}
REQUIRED_FLUX_T2I = {
    "UNETLoader": ("unet_name", "weight_dtype"),
    "DualCLIPLoader": ("clip_name1", "clip_name2", "type"),
    "VAELoader": ("vae_name",),
    "CLIPTextEncodeFlux": ("clip", "clip_l", "t5xxl", "guidance"),
    "EmptyLatentImage": ("width", "height", "batch_size"),
    "KSampler": ("model", "seed", "steps", "cfg", "sampler_name", "scheduler",
                 "positive", "negative", "latent_image", "denoise"),
    "VAEDecode": ("samples", "vae"),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_BACKROOMS_FLUX_T2I = {  # 2026-10-04
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "FluxGuidance": ("conditioning", "guidance"),
    "EmptyLatentImage": ("width", "height", "batch_size"),
    "ModelSamplingFlux": ("model", "max_shift", "base_shift", "width", "height"),
    "KSampler": ("model", "seed", "steps", "cfg", "sampler_name", "scheduler",
                 "positive", "negative", "latent_image", "denoise"),
    "VAEDecode": ("samples", "vae"),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_FACE_DETAIL = {
    "UltralyticsDetectorProvider": ("model_name",),
    "FaceDetailer": (
        "image", "model", "clip", "vae", "guide_size", "guide_size_for", "max_size",
        "seed", "steps", "cfg", "sampler_name", "scheduler", "positive", "negative",
        "denoise", "feather", "noise_mask", "force_inpaint", "bbox_threshold",
        "bbox_dilation", "bbox_crop_factor", "sam_detection_hint", "sam_dilation",
        "sam_threshold", "sam_bbox_expansion", "sam_mask_hint_threshold",
        "sam_mask_hint_use_negative", "drop_size", "bbox_detector", "wildcard", "cycle",
    ),
}
REQUIRED_IDENTITY_FACE_REFINE = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "LoadImage": ("image",),
    "IPAdapterModelLoader": ("ipadapter_file",),
    "CLIPVisionLoader": ("clip_name",),
    "IPAdapterAdvanced": (
        "model", "ipadapter", "image", "weight", "weight_type",
        "combine_embeds", "start_at", "end_at", "embeds_scaling",
    ),
    "UltralyticsDetectorProvider": ("model_name",),
    "FaceDetailer": REQUIRED_FACE_DETAIL["FaceDetailer"],
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_LIVEPORTRAIT_EXPRESSION = {
    "LoadImage": ("image",),
    "ExpressionEditor": (
        "rotate_pitch", "rotate_yaw", "rotate_roll", "blink", "eyebrow",
        "wink", "pupil_x", "pupil_y", "aaa", "eee", "woo", "smile",
        "src_ratio", "sample_ratio", "crop_factor",
    ),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_HAND_CROP_INPAINT = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "LoadImage": ("image",),
    "InpaintCropImproved": (
        "image", "downscale_algorithm", "upscale_algorithm", "preresize",
        "preresize_mode", "preresize_min_width", "preresize_min_height",
        "preresize_max_width", "preresize_max_height", "mask_fill_holes",
        "mask_expand_pixels", "mask_invert", "mask_blend_pixels",
        "mask_hipass_filter", "extend_for_outpainting", "extend_up_factor",
        "extend_down_factor", "extend_left_factor", "extend_right_factor",
        "context_from_mask_extend_factor", "output_resize_to_target_size",
        "output_target_width", "output_target_height", "output_padding",
        "device_mode",
    ),
    "VAEEncodeForInpaint": ("pixels", "vae", "mask", "grow_mask_by"),
    "KSampler": (
        "model", "seed", "steps", "cfg", "sampler_name", "scheduler",
        "positive", "negative", "latent_image", "denoise",
    ),
    "VAEDecode": ("samples", "vae"),
    "InpaintStitchImproved": ("stitcher", "inpainted_image"),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_HAND_DETAILER = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "LoadImage": ("image",),
    "UltralyticsDetectorProvider": ("model_name",),
    "BboxDetectorSEGS": (
        "bbox_detector", "image", "threshold", "dilation", "crop_factor",
        "drop_size", "labels",
    ),
    "ImpactSEGSOrderedFilter": (
        "segs", "target", "order", "take_start", "take_count",
    ),
    "DetailerForEach": (
        "image", "segs", "model", "clip", "vae", "guide_size",
        "guide_size_for", "max_size", "seed", "steps", "cfg",
        "sampler_name", "scheduler", "positive", "negative", "denoise",
        "feather", "noise_mask", "force_inpaint", "wildcard", "cycle",
    ),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_HAND_REFINER_SD15 = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "LoadImage": ("image",),
    "InpaintCropImproved": REQUIRED_HAND_CROP_INPAINT["InpaintCropImproved"],
    # The tuning controls are optional in the live ComfyUI schema. They are
    # still supplied in the graph, but only IMAGE is a required socket.
    "MeshGraphormer-DepthMapPreprocessor": ("image",),
    "VAEEncode": ("pixels", "vae"),
    "SetLatentNoiseMask": ("samples", "mask"),
    "ControlNetLoader": ("control_net_name",),
    "ControlNetApplyAdvanced": REQUIRED_POSE_CONTROL["ControlNetApplyAdvanced"],
    "KSampler": REQUIRED_T2I["KSampler"],
    "VAEDecode": ("samples", "vae"),
    "InpaintStitchImproved": ("stitcher", "inpainted_image"),
    "SaveImage": ("images", "filename_prefix"),
}
REQUIRED_HAND_OPENPOSE_SDXL = {
    "CheckpointLoaderSimple": ("ckpt_name",),
    "CLIPTextEncode": ("text", "clip"),
    "LoadImage": ("image",),
    "InpaintCropImproved": REQUIRED_HAND_CROP_INPAINT["InpaintCropImproved"],
    "VAEEncode": ("pixels", "vae"),
    "SetLatentNoiseMask": ("samples", "mask"),
    "ControlNetLoader": ("control_net_name",),
    "SetUnionControlNetType": ("control_net", "type"),
    "ControlNetApplyAdvanced": REQUIRED_POSE_CONTROL["ControlNetApplyAdvanced"],
    "KSampler": REQUIRED_T2I["KSampler"],
    "VAEDecode": ("samples", "vae"),
    "InpaintStitchImproved": ("stitcher", "inpainted_image"),
    "SaveImage": ("images", "filename_prefix"),
}


class ImageRenderError(RuntimeError):
    pass


def _get_json(url: str, timeout: int = 8) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ImageRenderError(f"ComfyUI API unavailable at {url}: {exc}") from exc


def object_info(api: str = API) -> dict:
    return _get_json(f"{api}/object_info")


def _required_inputs(node: dict) -> set[str]:
    return set((node.get("input") or {}).get("required") or {})


def validate_nodes(info: dict, mode: str, *, profile: str = "realvisxl",
                   face_detail: bool = False) -> None:
    if mode == "liveportrait_expression":
        requirements = dict(REQUIRED_LIVEPORTRAIT_EXPRESSION)
    elif mode == "hand_crop_inpaint":
        requirements = dict(REQUIRED_HAND_CROP_INPAINT)
    elif mode == "hand_detailer":
        requirements = dict(REQUIRED_HAND_DETAILER)
    elif mode == "hand_refiner_sd15":
        requirements = dict(REQUIRED_HAND_REFINER_SD15)
    elif mode == "hand_openpose_sdxl":
        requirements = dict(REQUIRED_HAND_OPENPOSE_SDXL)
    elif mode == "face_refine_identity":
        requirements = dict(REQUIRED_IDENTITY_FACE_REFINE)
    else:
        requirements = dict(REQUIRED_FLUX_T2I if profile == "realpro_flux"
                            else REQUIRED_BACKROOMS_FLUX_T2I if profile == "backrooms_flux" else REQUIRED_T2I)
    if mode in {"i2i", "i2i_identity"}:
        requirements.update(REQUIRED_I2I)
        if mode == "i2i_identity":
            requirements.update(REQUIRED_IDENTITY_I2I)
    elif mode in {"inpaint_identity", "inpaint_identity_pose"}:
        requirements.update(REQUIRED_IDENTITY_INPAINT)
        if mode == "inpaint_identity_pose":
            requirements.update(REQUIRED_POSE_CONTROL)
    if face_detail:
        requirements.update(REQUIRED_FACE_DETAIL)
    missing: list[str] = []
    for node_name, inputs in requirements.items():
        actual = info.get(node_name)
        if not actual:
            missing.append(f"missing node {node_name}")
            continue
        absent = set(inputs) - _required_inputs(actual)
        if absent:
            missing.append(f"{node_name} missing inputs {', '.join(sorted(absent))}")
    if missing:
        raise ImageRenderError("live ComfyUI does not support this graph: " + "; ".join(missing))


def _safe_segment(value: str, label: str) -> str:
    value = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in value.strip())
    value = value.strip("-_")
    if not value or value in {".", ".."}:
        raise ImageRenderError(f"{label} must contain letters or numbers")
    return value[:80]


def story_dir(story: str) -> Path:
    target = (STORY_ROOT / _safe_segment(story, "story")).resolve()
    root = STORY_ROOT.resolve()
    if root not in target.parents:
        raise ImageRenderError("story output must remain under outputs/stories")
    return target


def build_graph(*, mode: str, prompt: str, negative: str, model: str,
                seed: int, width: int, height: int, steps: int, cfg: float,
                sampler: str, scheduler: str, denoise: float, prefix: str,
                reference_name: str | None = None, hires_fix: bool = True,
                face_detail: bool = False, profile: str = "realvisxl",
                lora_name: str | None = None, lora_strength: float = 0.5,
                mask_name: str | None = None, identity_name: str | None = None,
                identity_weight: float = 0.85, pose_name: str | None = None,
                pose_strength: float = 1.0, pose_end_percent: float = 0.92,
                smile_strength: float = 1.0,
                mouth_open: float = 0.0, liveportrait_crop_factor: float = 2.0,
                grow_mask_by: int = 8,
                use_latent_noise_mask: bool = False) -> dict:
    """Build a guarded ComfyUI graph; caller validates its selected nodes first."""
    if mode not in {
            "t2i", "i2i", "i2i_identity", "inpaint_identity", "inpaint_identity_pose",
            "face_refine_identity", "liveportrait_expression",
            "hand_crop_inpaint", "hand_detailer", "hand_refiner_sd15",
            "hand_openpose_sdxl"}:
        raise ImageRenderError(
            "mode must be t2i, i2i, i2i_identity, inpaint_identity, inpaint_identity_pose, "
            "face_refine_identity, liveportrait_expression, hand_crop_inpaint, "
            "hand_detailer, hand_refiner_sd15, or hand_openpose_sdxl"
        )
    if profile not in MODEL_PROFILES:
        raise ImageRenderError(f"unknown image model profile: {profile}")
    grow_mask_by = int(grow_mask_by)
    if grow_mask_by < 0 or grow_mask_by > 64:
        raise ImageRenderError("grow_mask_by must be between 0 and 64")
    if mode == "liveportrait_expression":
        if not reference_name:
            raise ImageRenderError("liveportrait_expression requires reference_name")
        if not -0.3 <= float(smile_strength) <= 1.3:
            raise ImageRenderError("smile_strength must be between -0.3 and 1.3")
        if not -30 <= float(mouth_open) <= 120:
            raise ImageRenderError("mouth_open must be between -30 and 120")
        if not 1.5 <= float(liveportrait_crop_factor) <= 3.0:
            raise ImageRenderError("liveportrait_crop_factor must be between 1.5 and 3.0")
        # AdvancedLivePortrait retargets facial landmarks and composites the
        # result over the untouched source. No diffusion checkpoint, VAE, or
        # text prompt participates, so the accepted body/room/wave pixels are
        # not regenerated merely to change the expression.
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": reference_name}},
            "2": {"class_type": "ExpressionEditor", "inputs": {
                "rotate_pitch": 0.0, "rotate_yaw": 0.0, "rotate_roll": 0.0,
                "blink": 0.0, "eyebrow": 0.0, "wink": 0.0,
                "pupil_x": 0.0, "pupil_y": 0.0,
                "aaa": float(mouth_open), "eee": 0.0, "woo": 0.0,
                "smile": float(smile_strength), "src_ratio": 1.0,
                "sample_ratio": 1.0, "crop_factor": float(liveportrait_crop_factor),
                "src_image": ["1", 0],
            }},
            "3": {"class_type": "SaveImage", "inputs": {
                "images": ["2", 0], "filename_prefix": prefix}},
        }
    if mode == "hand_crop_inpaint":
        if not reference_name or not mask_name:
            raise ImageRenderError(
                "hand_crop_inpaint requires reference_name and mask_name"
            )
        # Crop around the small hand mask, enlarge it to SDXL working
        # resolution, sample only that crop, then stitch it into the immutable
        # source.  This avoids regenerating the accepted face, body, or room.
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative, "clip": ["1", 1]}},
            "8": {"class_type": "LoadImage", "inputs": {
                "image": reference_name}},
            "9": {"class_type": "LoadImage", "inputs": {
                "image": mask_name}},
            "10": {"class_type": "InpaintCropImproved", "inputs": {
                "image": ["8", 0], "mask": ["9", 1],
                "downscale_algorithm": "bilinear",
                "upscale_algorithm": "bicubic", "preresize": False,
                "preresize_mode": "ensure minimum resolution",
                "preresize_min_width": 1024, "preresize_min_height": 1024,
                "preresize_max_width": 16384, "preresize_max_height": 16384,
                "mask_fill_holes": True, "mask_expand_pixels": 4,
                "mask_invert": False, "mask_blend_pixels": 12,
                "mask_hipass_filter": 0.05, "extend_for_outpainting": False,
                "extend_up_factor": 1.0, "extend_down_factor": 1.0,
                "extend_left_factor": 1.0, "extend_right_factor": 1.0,
                "context_from_mask_extend_factor": 2.6,
                "output_resize_to_target_size": True,
                "output_target_width": 768, "output_target_height": 768,
                "output_padding": "32", "device_mode": "cpu (compatible)"}},
            "4": {"class_type": "VAEEncode", "inputs": {
                "pixels": ["10", 1], "vae": ["1", 2]}},
            "12": {"class_type": "SetLatentNoiseMask", "inputs": {
                "samples": ["4", 0], "mask": ["10", 2]}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": int(seed), "steps": int(steps),
                "cfg": float(cfg), "sampler_name": sampler,
                "scheduler": scheduler, "positive": ["2", 0],
                "negative": ["3", 0], "latent_image": ["12", 0],
                "denoise": float(denoise)}},
            "6": {"class_type": "VAEDecode", "inputs": {
                "samples": ["5", 0], "vae": ["1", 2]}},
            "11": {"class_type": "InpaintStitchImproved", "inputs": {
                "stitcher": ["10", 0], "inpainted_image": ["6", 0]}},
            "7": {"class_type": "SaveImage", "inputs": {
                "images": ["11", 0], "filename_prefix": prefix}},
        }
    if mode == "hand_detailer":
        if not reference_name:
            raise ImageRenderError("hand_detailer requires reference_name")
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative, "clip": ["1", 1]}},
            "8": {"class_type": "LoadImage", "inputs": {
                "image": reference_name}},
            "11": {"class_type": "UltralyticsDetectorProvider", "inputs": {
                "model_name": HAND_DETAIL_MODEL}},
            "13": {"class_type": "BboxDetectorSEGS", "inputs": {
                "bbox_detector": ["11", 0], "image": ["8", 0],
                "threshold": 0.25, "dilation": 16, "crop_factor": 4.0,
                "drop_size": 8, "labels": "all"}},
            # The source has one raised hand near the ceiling and one lowered
            # hand near the waist.  Select only the topmost detection; applying
            # a generic FaceDetailer directly to the detector edited both and
            # created a spurious second palm on the lowered arm.
            "14": {"class_type": "ImpactSEGSOrderedFilter", "inputs": {
                "segs": ["13", 0], "target": "y1", "order": False,
                "take_start": 0, "take_count": 1}},
            "12": {"class_type": "DetailerForEach", "inputs": {
                "image": ["8", 0], "model": ["1", 0], "clip": ["1", 1],
                "segs": ["14", 0],
                "vae": ["1", 2], "guide_size": 768, "guide_size_for": True,
                "max_size": 1024, "seed": int(seed), "steps": int(steps),
                "cfg": float(cfg), "sampler_name": sampler,
                "scheduler": scheduler, "positive": ["2", 0],
                "negative": ["3", 0], "denoise": float(denoise),
                "feather": 8, "noise_mask": True, "force_inpaint": True,
                "wildcard": "", "cycle": 1}},
            "7": {"class_type": "SaveImage", "inputs": {
                "images": ["12", 0], "filename_prefix": prefix}},
        }
    if mode == "hand_refiner_sd15":
        if not reference_name or not mask_name:
            raise ImageRenderError(
                "hand_refiner_sd15 requires reference_name and a raised-hand mask"
            )
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative, "clip": ["1", 1]}},
            "8": {"class_type": "LoadImage", "inputs": {
                "image": reference_name}},
            "9": {"class_type": "LoadImage", "inputs": {"image": mask_name}},
            "10": {"class_type": "InpaintCropImproved", "inputs": {
                "image": ["8", 0], "mask": ["9", 1],
                "downscale_algorithm": "bicubic", "upscale_algorithm": "bicubic",
                "preresize": False,
                "preresize_mode": "ensure minimum resolution",
                "preresize_min_width": 768, "preresize_min_height": 768,
                "preresize_max_width": 768, "preresize_max_height": 768,
                "mask_fill_holes": True, "mask_expand_pixels": 10,
                "mask_invert": False, "mask_blend_pixels": 8,
                "mask_hipass_filter": 0.0, "extend_for_outpainting": False,
                "extend_up_factor": 1.0, "extend_down_factor": 1.0,
                "extend_left_factor": 1.0, "extend_right_factor": 1.0,
                "context_from_mask_extend_factor": 3.0,
                "output_resize_to_target_size": True,
                "output_target_width": 768, "output_target_height": 768,
                "output_padding": "32", "device_mode": "cpu (compatible)"}},
            # Reconstruct a 3D hand depth map from only the raised-hand crop.
            # This avoids the unconstrained SDXL detailer failures (four digits,
            # extra palm, and claw) while the crop/stitch path preserves the rest.
            "15": {"class_type": "MeshGraphormer-DepthMapPreprocessor", "inputs": {
                "image": ["10", 1], "mask_bbox_padding": 24,
                "resolution": 512, "mask_type": "tight_bboxes",
                "mask_expand": 6, "rand_seed": int(seed),
                "detect_thr": 0.45, "presence_thr": 0.45}},
            "4": {"class_type": "VAEEncode", "inputs": {
                "pixels": ["10", 1], "vae": ["1", 2]}},
            "16": {"class_type": "SetLatentNoiseMask", "inputs": {
                "samples": ["4", 0], "mask": ["15", 1]}},
            "17": {"class_type": "ControlNetLoader", "inputs": {
                "control_net_name": HAND_REFINER_CONTROLNET}},
            "18": {"class_type": "ControlNetApplyAdvanced", "inputs": {
                "positive": ["2", 0], "negative": ["3", 0],
                "control_net": ["17", 0], "image": ["15", 0],
                "strength": 0.80, "start_percent": 0.0,
                "end_percent": 1.0}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": int(seed), "steps": int(steps),
                "cfg": float(cfg), "sampler_name": sampler,
                "scheduler": scheduler, "positive": ["18", 0],
                "negative": ["18", 1], "latent_image": ["16", 0],
                "denoise": float(denoise)}},
            "6": {"class_type": "VAEDecode", "inputs": {
                "samples": ["5", 0], "vae": ["1", 2]}},
            "11": {"class_type": "InpaintStitchImproved", "inputs": {
                "stitcher": ["10", 0], "inpainted_image": ["6", 0]}},
            "7": {"class_type": "SaveImage", "inputs": {
                "images": ["11", 0], "filename_prefix": prefix}},
        }
    if mode == "hand_openpose_sdxl":
        if not reference_name or not mask_name or not pose_name:
            raise ImageRenderError(
                "hand_openpose_sdxl requires reference, raised-hand mask, and pose map"
            )
        crop_inputs = {
            "downscale_algorithm": "bicubic", "upscale_algorithm": "bicubic",
            "preresize": False,
            "preresize_mode": "ensure minimum resolution",
            "preresize_min_width": 1024, "preresize_min_height": 1024,
            "preresize_max_width": 1024, "preresize_max_height": 1024,
            "mask_fill_holes": True, "mask_expand_pixels": 8,
            "mask_invert": False, "mask_blend_pixels": 8,
            "mask_hipass_filter": 0.0, "extend_for_outpainting": False,
            "extend_up_factor": 1.0, "extend_down_factor": 1.0,
            "extend_left_factor": 1.0, "extend_right_factor": 1.0,
            "context_from_mask_extend_factor": 3.0,
            "output_resize_to_target_size": True,
            "output_target_width": 1024, "output_target_height": 1024,
            "output_padding": "32", "device_mode": "cpu (compatible)",
        }
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {
                "ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {
                "text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {
                "text": negative, "clip": ["1", 1]}},
            "8": {"class_type": "LoadImage", "inputs": {
                "image": reference_name}},
            "9": {"class_type": "LoadImage", "inputs": {"image": mask_name}},
            "19": {"class_type": "LoadImage", "inputs": {"image": pose_name}},
            "10": {"class_type": "InpaintCropImproved", "inputs": {
                "image": ["8", 0], "mask": ["9", 1], **crop_inputs}},
            # Crop the full-frame 21-joint target with the exact same mask and
            # geometry as the source. This keeps the pose pixels registered to
            # the hand crop instead of asking a full-body pose map to steer it.
            "20": {"class_type": "InpaintCropImproved", "inputs": {
                "image": ["19", 0], "mask": ["9", 1], **crop_inputs}},
            "4": {"class_type": "VAEEncode", "inputs": {
                "pixels": ["10", 1], "vae": ["1", 2]}},
            "12": {"class_type": "SetLatentNoiseMask", "inputs": {
                "samples": ["4", 0], "mask": ["10", 2]}},
            "17": {"class_type": "ControlNetLoader", "inputs": {
                "control_net_name": CONTROLNET_UNION_SDXL}},
            "21": {"class_type": "SetUnionControlNetType", "inputs": {
                "control_net": ["17", 0], "type": "openpose"}},
            "18": {"class_type": "ControlNetApplyAdvanced", "inputs": {
                "positive": ["2", 0], "negative": ["3", 0],
                "control_net": ["21", 0], "image": ["20", 1],
                "strength": float(pose_strength), "start_percent": 0.0,
                "end_percent": float(pose_end_percent), "vae": ["1", 2]}},
            "5": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": int(seed), "steps": int(steps),
                "cfg": float(cfg), "sampler_name": sampler,
                "scheduler": scheduler, "positive": ["18", 0],
                "negative": ["18", 1], "latent_image": ["12", 0],
                "denoise": float(denoise)}},
            "6": {"class_type": "VAEDecode", "inputs": {
                "samples": ["5", 0], "vae": ["1", 2]}},
            "11": {"class_type": "InpaintStitchImproved", "inputs": {
                "stitcher": ["10", 0], "inpainted_image": ["6", 0]}},
            "7": {"class_type": "SaveImage", "inputs": {
                "images": ["11", 0], "filename_prefix": prefix}},
        }
    if lora_name and (profile != 'realvisxl' or Path(lora_name).name != lora_name
                      or any(c in lora_name for c in '/\\*?') or not 0 <= lora_strength <= 1):
        raise ImageRenderError('SDXL LoRA requires realvisxl, a plain installed filename, and strength 0..1')
    if mode in {"inpaint_identity", "inpaint_identity_pose", "face_refine_identity"} and lora_name:
        raise ImageRenderError(
            "identity inpaint plus a checkpoint LoRA is not validated in the isolated C001 test"
        )
    if profile == "alicemix_sd15":
        # The named negative embeddings are intentionally not included: they
        # are absent locally and pretending otherwise would make a recipe look
        # reproducible when it is not.  The literal quality/anatomy weights
        # remain, together with the renderer's stronger general negative.
        prompt = f"{ALICEMIX_POSITIVE_PREFIX}, {prompt}"
        negative = f"{negative}, {ALICEMIX_NEGATIVE_SUFFIX}"
    if profile == "backrooms_flux":
        # 2026-10-04: exactly the Backrooms still graph (nodes 1-9): flux1-dev-fp8 checkpoint, FluxGuidance 3.5,
        # ModelSamplingFlux 1.15/0.5 at the render size, KSampler euler/simple cfg 1.0 (12 steps by default).
        if mode != "t2i":
            raise ImageRenderError("backrooms_flux supports text-to-image only; a character's face goes through the "
                                   "GVD identity still (execute_narrative_scene, FLUX.2 Klein + reference image)")
        if face_detail:
            raise ImageRenderError("backrooms_flux has no face-detail pass (the Backrooms stills use none)")
        if not prompt.strip():
            raise ImageRenderError("prompt is required")
        if width < 256 or height < 256 or width % 16 or height % 16:
            raise ImageRenderError("backrooms_flux width and height must be multiples of 16 and at least 256")
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
            "4": {"class_type": "FluxGuidance", "inputs": {"conditioning": ["2", 0], "guidance": 3.5}},
            "5": {"class_type": "EmptyLatentImage", "inputs": {"width": int(width), "height": int(height),
                                                                "batch_size": 1}},
            "6": {"class_type": "ModelSamplingFlux", "inputs": {"model": ["1", 0], "max_shift": 1.15,
                                                                 "base_shift": 0.5, "width": int(width),
                                                                 "height": int(height)}},
            "7": {"class_type": "KSampler", "inputs": {"model": ["6", 0], "seed": int(seed), "steps": int(steps),
                                                        "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
                                                        "positive": ["4", 0], "negative": ["3", 0],
                                                        "latent_image": ["5", 0], "denoise": 1.0}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
        }
    if profile == "realpro_flux":
        if mode != "t2i":
            raise ImageRenderError("realpro_flux currently supports text-to-image only")
        if face_detail:
            raise ImageRenderError("realpro_flux face_detail is not available until the isolated custom-node startup is repaired")
        # Flux's text encoders carry classifier-free guidance internally.
        # A normal SDXL CFG/hi-res pass is not compatible and can exhaust the
        # 16 GB card with this 11.9 GB UNet.
        graph = {
            "1": {"class_type": "UNETLoader", "inputs": {"unet_name": model, "weight_dtype": "default"}},
            "2": {"class_type": "DualCLIPLoader", "inputs": {
                "clip_name1": "clip_l.safetensors", "clip_name2": "t5xxl_fp16.safetensors",
                "type": "flux", "device": "cpu"}},
            "3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
            "4": {"class_type": "CLIPTextEncodeFlux", "inputs": {
                "clip": ["2", 0], "clip_l": prompt, "t5xxl": prompt, "guidance": 3.5}},
            "5": {"class_type": "CLIPTextEncodeFlux", "inputs": {
                "clip": ["2", 0], "clip_l": "", "t5xxl": "", "guidance": 3.5}},
            "6": {"class_type": "EmptyLatentImage", "inputs": {
                "width": int(width), "height": int(height), "batch_size": 1}},
            "7": {"class_type": "KSampler", "inputs": {
                "model": ["1", 0], "seed": int(seed), "steps": int(steps), "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple", "positive": ["4", 0],
                "negative": ["5", 0], "latent_image": ["6", 0], "denoise": 1.0}},
            "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["3", 0]}},
            "9": {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": prefix}},
        }
        return graph
    if not prompt.strip():
        raise ImageRenderError("prompt is required")
    if width < 256 or height < 256 or width % 8 or height % 8:
        raise ImageRenderError("width and height must be multiples of 8 and at least 256")
    if not 0 <= denoise <= 1:
        raise ImageRenderError("denoise must be between 0 and 1")
    if not 0 <= identity_weight <= 2:
        raise ImageRenderError("identity_weight must be between 0 and 2")
    if mode in {"inpaint_identity", "inpaint_identity_pose"} and (
            not reference_name or not mask_name or not identity_name):
        raise ImageRenderError(
            "identity inpaint requires reference_name, mask_name, and identity_name"
        )
    if mode == "inpaint_identity_pose" and not pose_name:
        raise ImageRenderError("inpaint_identity_pose requires pose_name")
    if mode in {"face_refine_identity", "i2i_identity"} and (
            not reference_name or not identity_name):
        raise ImageRenderError(
            f"{mode} requires reference_name and identity_name"
        )
    if not 0 <= pose_strength <= 2:
        raise ImageRenderError("pose_strength must be between 0 and 2")
    if not 0 <= pose_end_percent <= 1:
        raise ImageRenderError("pose_end_percent must be between 0 and 1")
    if mode == "face_refine_identity":
        # Work at detector-crop resolution instead of attempting to synthesize
        # a mouth inside the roughly 11x7 latent-pixel region of the 1024x768
        # full frame. The source image is passed straight into FaceDetailer, so
        # all pixels outside the detected face remain unchanged.
        return {
            "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
            "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
            "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
            "8": {"class_type": "LoadImage", "inputs": {"image": reference_name}},
            "15": {"class_type": "IPAdapterModelLoader", "inputs": {
                "ipadapter_file": IPADAPTER_SDXL_FACE}},
            "16": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": CLIP_VISION_H}},
            "18": {"class_type": "LoadImage", "inputs": {"image": identity_name}},
            "17": {"class_type": "IPAdapterAdvanced", "inputs": {
                "model": ["1", 0], "ipadapter": ["15", 1], "image": ["18", 0],
                "weight": float(identity_weight), "weight_type": "linear",
                "combine_embeds": "concat", "start_at": 0.0, "end_at": 0.85,
                "embeds_scaling": "K+V w/ C penalty", "clip_vision": ["16", 0]}},
            "11": {"class_type": "UltralyticsDetectorProvider", "inputs": {
                "model_name": FACE_DETAIL_MODEL}},
            "12": {"class_type": "FaceDetailer", "inputs": {
                "image": ["8", 0], "model": ["17", 0], "clip": ["1", 1], "vae": ["1", 2],
                "guide_size": 768, "guide_size_for": True, "max_size": 1024,
                "seed": int(seed), "steps": int(steps), "cfg": float(cfg),
                "sampler_name": sampler, "scheduler": scheduler,
                "positive": ["2", 0], "negative": ["3", 0],
                "denoise": float(denoise), "feather": 12, "noise_mask": True,
                "force_inpaint": True, "bbox_threshold": 0.45,
                "bbox_dilation": 8, "bbox_crop_factor": 2.2,
                "sam_detection_hint": "center-1", "sam_dilation": 0,
                "sam_threshold": 0.93, "sam_bbox_expansion": 0,
                "sam_mask_hint_threshold": 0.70,
                "sam_mask_hint_use_negative": "False", "drop_size": 10,
                "bbox_detector": ["11", 0], "wildcard": "", "cycle": 1}},
            "7": {"class_type": "SaveImage", "inputs": {
                "images": ["12", 0], "filename_prefix": prefix}},
        }
    if mode == "t2i":
        # t2i starts from a pure-noise EmptyLatentImage. Any denoise below 1.0
        # tells KSampler to stop partway through removing that noise, which
        # leaves a visible haze/fog baked into the whole frame rather than a
        # clean image — this is not a subtle quality knob, it produces
        # unmistakably bad output. i2i denoise (a real partial-strength value,
        # used to preserve some of a reference image) is unaffected. Enforced
        # here rather than left to callers because a caller-supplied value
        # (including one a chat model invents on its own, as happened in
        # production) can silently reintroduce this exact bug otherwise.
        denoise = 1.0
    # Two full-body figures in one frame leaves each face rendered at a small
    # fraction of the base resolution — well inside the range where SDXL
    # reliably produces crossed/misaligned eyes and other small-feature
    # artifacts. A hi-res fix (resample the first pass's latent larger, then
    # run a short low-denoise refinement pass) gives the model far more
    # pixels per face before the image is finalized, which is the standard
    # fix for exactly this symptom. Applied automatically for t2i; i2i is
    # left as a single pass for now since its denoise semantics differ.
    # The requested AliceMix recipe uses a named RealESRGAN x4minus upscaler
    # that is not installed (only x2/x4plus variants are present).  Do not
    # silently substitute an upscaler or use the renderer's latent bislerp
    # substitute; its base recipe remains faithful until the exact asset is
    # supplied. RealVisXL keeps its tested latent hi-res pass.
    apply_hires = hires_fix and mode == "t2i" and profile != "alicemix_sd15"
    final_latent_ref = ["10", 0] if apply_hires else ["5", 0]
    final_image_ref = ["12", 0] if face_detail else ["6", 0]
    if mode in {"inpaint_identity", "inpaint_identity_pose"}:
        final_image_ref = ["10", 0]
    graph = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": model}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["1", 1]}},
        "5": {"class_type": "KSampler", "inputs": {
            "model": ["17", 0] if mode in {"inpaint_identity", "inpaint_identity_pose"} else ["1", 0],
            "seed": int(seed), "steps": int(steps), "cfg": float(cfg),
            "sampler_name": sampler, "scheduler": scheduler, "positive": ["2", 0],
            "negative": ["3", 0], "latent_image": ["4", 0], "denoise": float(denoise)}},
        "6": {"class_type": "VAEDecode", "inputs": {"samples": final_latent_ref, "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage", "inputs": {"images": final_image_ref, "filename_prefix": prefix}},
    }
    if mode == "t2i":
        graph["4"] = {"class_type": "EmptyLatentImage", "inputs": {
            "width": int(width), "height": int(height), "batch_size": 1}}
    elif mode in {"i2i", "i2i_identity"}:
        if not reference_name:
            raise ImageRenderError("reference_name is required for i2i")
        graph["4"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["8", 0], "vae": ["1", 2]}}
        graph["8"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
        if mode == "i2i_identity":
            graph["15"] = {"class_type": "IPAdapterModelLoader", "inputs": {
                "ipadapter_file": IPADAPTER_SDXL_FACE}}
            graph["16"] = {"class_type": "CLIPVisionLoader", "inputs": {
                "clip_name": CLIP_VISION_H}}
            graph["18"] = {"class_type": "LoadImage", "inputs": {
                "image": identity_name}}
            graph["17"] = {"class_type": "IPAdapterAdvanced", "inputs": {
                # Output 0 is MODEL; IPAdapterAdvanced requires the IPADAPTER
                # payload emitted as output 1.
                "model": ["1", 0], "ipadapter": ["15", 1], "image": ["18", 0],
                "weight": float(identity_weight), "weight_type": "linear",
                "combine_embeds": "concat", "start_at": 0.0, "end_at": 0.85,
                "embeds_scaling": "K+V w/ C penalty", "clip_vision": ["16", 0]}}
            graph["5"]["inputs"]["model"] = ["17", 0]
    else:
        graph["8"] = {"class_type": "LoadImage", "inputs": {"image": reference_name}}
        graph["9"] = {"class_type": "LoadImage", "inputs": {"image": mask_name}}
        graph["10"] = {"class_type": "ImageCompositeMasked", "inputs": {
            "destination": ["8", 0], "source": ["6", 0], "x": 0, "y": 0,
            "resize_source": False, "mask": ["9", 1]}}
        if use_latent_noise_mask and mode in {"inpaint_identity", "inpaint_identity_pose"}:
            # Preserve prefilled reference pixels in latent space; mask only
            # steers where KSampler may rewrite noise (unlike VAEEncodeForInpaint).
            graph["4"] = {"class_type": "VAEEncode", "inputs": {
                "pixels": ["8", 0], "vae": ["1", 2]}}
            graph["23"] = {"class_type": "SetLatentNoiseMask", "inputs": {
                "samples": ["4", 0], "mask": ["9", 1]}}
            graph["5"]["inputs"]["latent_image"] = ["23", 0]
        else:
            graph["4"] = {"class_type": "VAEEncodeForInpaint", "inputs": {
                "pixels": ["8", 0], "vae": ["1", 2], "mask": ["9", 1],
                "grow_mask_by": int(grow_mask_by)}}
        graph["15"] = {"class_type": "IPAdapterModelLoader", "inputs": {
            "ipadapter_file": IPADAPTER_SDXL_FACE}}
        graph["16"] = {"class_type": "CLIPVisionLoader", "inputs": {
            "clip_name": CLIP_VISION_H}}
        graph["18"] = {"class_type": "LoadImage", "inputs": {"image": identity_name}}
        graph["17"] = {"class_type": "IPAdapterAdvanced", "inputs": {
                "model": ["1", 0], "ipadapter": ["15", 1], "image": ["18", 0],
            "weight": float(identity_weight), "weight_type": "linear",
            "combine_embeds": "concat", "start_at": 0.0, "end_at": 0.85,
            "embeds_scaling": "K+V w/ C penalty", "clip_vision": ["16", 0]}}
        if mode == "inpaint_identity_pose":
            graph["19"] = {"class_type": "ControlNetLoader", "inputs": {
                "control_net_name": CONTROLNET_UNION_SDXL}}
            graph["20"] = {"class_type": "SetUnionControlNetType", "inputs": {
                "control_net": ["19", 0], "type": "openpose"}}
            graph["22"] = {"class_type": "LoadImage", "inputs": {"image": pose_name}}
            graph["21"] = {"class_type": "ControlNetApplyAdvanced", "inputs": {
                "positive": ["2", 0], "negative": ["3", 0],
                "control_net": ["20", 0], "image": ["22", 0],
                "strength": float(pose_strength), "start_percent": 0.0,
                "end_percent": 0.80, "vae": ["1", 2]}}
            graph["5"]["inputs"]["positive"] = ["21", 0]
            graph["5"]["inputs"]["negative"] = ["21", 1]
    if apply_hires:
        graph["9"] = {"class_type": "LatentUpscaleBy", "inputs": {
            "samples": ["5", 0], "scale_by": DEFAULT_HIRES_SCALE,
            "upscale_method": "bislerp"}}
        graph["10"] = {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": int(seed), "steps": DEFAULT_HIRES_STEPS,
            "cfg": float(cfg), "sampler_name": sampler, "scheduler": scheduler,
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["9", 0],
            "denoise": DEFAULT_HIRES_DENOISE}}
    if face_detail:
        # FaceDetailer operates after the base/hi-res image has been decoded.
        # It detects faces, enlarges only those regions, and uses a modest
        # denoise value so it can repair eyes without replacing the scene.
        graph["11"] = {"class_type": "UltralyticsDetectorProvider", "inputs": {
            "model_name": FACE_DETAIL_MODEL}}
        graph["13"] = {"class_type": "CLIPTextEncode", "inputs": {
            "text": f"{prompt}, {FACE_DETAIL_POSITIVE}", "clip": ["1", 1]}}
        graph["14"] = {"class_type": "CLIPTextEncode", "inputs": {
            "text": f"{negative}, {FACE_DETAIL_NEGATIVE}", "clip": ["1", 1]}}
        graph["12"] = {"class_type": "FaceDetailer", "inputs": {
            "image": ["6", 0], "model": ["1", 0], "clip": ["1", 1], "vae": ["1", 2],
            "guide_size": 768, "guide_size_for": True, "max_size": 1024, "seed": int(seed),
            "steps": 18, "cfg": 5.5, "sampler_name": sampler, "scheduler": scheduler,
            "positive": ["13", 0], "negative": ["14", 0], "denoise": 0.30,
            "feather": 8, "noise_mask": True, "force_inpaint": True,
            "bbox_threshold": 0.35, "bbox_dilation": 10, "bbox_crop_factor": 3.0,
            "sam_detection_hint": "none", "sam_dilation": 0, "sam_threshold": 0.93,
            "sam_bbox_expansion": 0, "sam_mask_hint_threshold": 0.7,
            "sam_mask_hint_use_negative": "False", "drop_size": 10,
            "bbox_detector": ["11", 0], "wildcard": "", "cycle": 1}}
    if lora_name:
        for node in graph.values():
            for key, value in node['inputs'].items():
                if key == 'model' and value == ['1', 0]:
                    node['inputs'][key] = ['15', 0]
                elif key == 'clip' and value == ['1', 1]:
                    node['inputs'][key] = ['15', 1]
        graph['15'] = {'class_type': 'LoraLoader', 'inputs': {
            'model': ['1', 0], 'clip': ['1', 1], 'lora_name': lora_name,
            'strength_model': lora_strength, 'strength_clip': lora_strength}}
    return graph


def _port_open(port: int = 8188) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _live_owner() -> bool:
    if not OWNER.is_file():
        return False
    try:
        pid = int(json.loads(OWNER.read_text(encoding="utf-8-sig")).get("pid") or 0)
    except Exception:
        return False
    if pid <= 0:
        return False
    return _pid_alive(pid)


def preflight_execute() -> None:
    """Do not claim, stop, or reuse a backend owned by someone else."""
    if _live_owner():
        raise ImageRenderError("refused: an Equal Shares render owns the GPU")
    if _port_open():
        raise ImageRenderError("refused: another ComfyUI backend is already listening on port 8188")
    thermal_guard.wait_before_render(lambda message: print(message, flush=True))


def _write_owner() -> None:
    with process_lock(IMAGE_OWNER.with_suffix(".lock")):
        _write_owner_locked()


def _write_owner_locked() -> None:
    IMAGE_OWNER.parent.mkdir(parents=True, exist_ok=True)
    if IMAGE_OWNER.is_file():
        try:
            old = json.loads(IMAGE_OWNER.read_text(encoding="utf-8"))
            old_pid = int(old.get("pid") or 0)
            if (old_pid and _pid_alive(old_pid)) or _pid_alive(int(old.get("backend_pid") or 0)):
                raise ImageRenderError(f"refused: image renderer is already owned by pid {old_pid}")
        except ImageRenderError:
            raise
        except Exception as exc:
            raise ImageRenderError("unreadable owner state; refusing replacement") from exc
        snapshot = IMAGE_OWNER.with_name(f"image_render_owner.{uuid.uuid4().hex}.json")
        snapshot.write_bytes(IMAGE_OWNER.read_bytes())
        IMAGE_OWNER.unlink()
    with IMAGE_OWNER.open("x", encoding="utf-8") as handle:
        json.dump({"pid": os.getpid(), "parent_pid": os.getppid(), "claimed_at": _now(),
                   "purpose": "general storyboard still image"}, handle, indent=2)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                capture_output=True, text=True, timeout=8)
        if not result.returncode and not result.stderr.strip():
            return any(len(row) > 1 and row[1] == str(pid)
                       for row in csv.reader(result.stdout.splitlines()))
        # Hardened Windows can deny tasklist for both live and dead PIDs.  A
        # read-only Get-Process lookup gives a second independent observation.
        # Preserve fail-closed behavior if that fallback itself cannot run.
        try:
            probe = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
                 "if($p){'LIVE'}else{'ABSENT'}"],
                capture_output=True, text=True, timeout=8,
            )
            state = probe.stdout.strip()
            if probe.returncode == 0 and state == "ABSENT":
                return False
            if probe.returncode == 0 and state == "LIVE":
                return True
        except Exception:
            pass
        return True  # genuinely unknown permissions never authorize clearing an owner
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _release_owner() -> None:
    with process_lock(IMAGE_OWNER.with_suffix(".lock")):
        _release_owner_locked()


def _release_owner_locked() -> None:
    IMAGE_OWNER.parent.mkdir(parents=True, exist_ok=True)
    if IMAGE_OWNER.is_file():
        owner = json.loads(IMAGE_OWNER.read_text(encoding="utf-8"))
        if owner.get("pid") != os.getpid():
            return
        child = int(owner.get("backend_pid") or 0)
        if child and _pid_alive(child):
            raise ImageRenderError(f"backend {child} still alive; retaining ownership evidence")
    IMAGE_OWNER.write_text(json.dumps({"pid": 0, "released_at": _now(),
                                       "purpose": "released"}, indent=2), encoding="utf-8")


def _backend_health(proc, command, stdout_path, stderr_path, state, **extra):
    record = {"state": state, "pid": proc.pid if proc else None, "command": command,
              "exit_code": proc.poll() if proc else None, "observed_at": _now(), **extra}
    record["logs"] = []
    for path in (stdout_path, stderr_path):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else []
        record["logs"].append({"path": str(path), "last_100_lines": lines[-100:]})
    path = stdout_path.with_suffix(f".health.{uuid.uuid4().hex}.json")
    with path.open("x", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    return record


# ComfyUI memory flags a caller may add to its own owned backend (2026-09-27, GVD runner RAM work).
# Anything else is refused: the backend's paths, port and listen address stay fixed here.
# 2026-09-28s: --use-sage-attention, as every MiniMax H3 renderer here launches (GVD Ref2VA row).
# 2026-09-28t: --disable-dynamic-vram (operator: weights stay on VRAM; ComfyUI's classic loader then
# logs "loaded completely" or "loaded partially" per model, which the caller can check).
ALLOWED_EXTRA_BACKEND_ARGS = frozenset({"--fast-disk", "--disable-pinned-memory", "--cache-none",
                                        "--use-sage-attention", "--disable-dynamic-vram"})


def _start_owned_backend(*, face_detail: bool = False, startup_timeout: float = 300,
                         extra_args: tuple[str, ...] = ()) -> subprocess.Popen:
    bad, items = [], list(extra_args)
    while items:
        flag = items.pop(0)
        if flag in ("--reserve-vram", "--vram-headroom"):  # flags with a value: GB of VRAM, 0-8
            value = items.pop(0) if items else ""
            try:
                ok = 0 <= float(value) <= 8
            except ValueError:
                ok = False
            if not ok:
                bad.append(f"{flag} {value!r}")
        elif flag not in ALLOWED_EXTRA_BACKEND_ARGS:
            bad.append(flag)
    if bad:
        raise ImageRenderError(f"backend flags not allowed: {bad}")
    if _port_open():
        raise ImageRenderError("port 8188 occupied immediately before launch")
    if not COMFY_PYTHON.is_file() or not (COMFY_ROOT / "main.py").is_file():
        raise ImageRenderError(f"ComfyUI runtime is unavailable at {COMFY_ROOT}")
    if not MODEL_PATHS.is_file():
        raise ImageRenderError(f"image model-path configuration missing: {MODEL_PATHS}")
    for directory in (IMAGE_INPUT, IMAGE_USER, IMAGE_TEMP, IMAGE_OUTPUT):
        directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    log_dir = IMAGE_RUNTIME / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / f"comfy_{stamp}.stdout.log"
    stderr_path = log_dir / f"comfy_{stamp}.stderr.log"
    args = [str(COMFY_PYTHON), "-u", "main.py", "--listen", "127.0.0.1", "--port", "8188",
            "--disable-auto-launch",
            "--extra-model-paths-config", str(MODEL_PATHS),
            "--input-directory", str(IMAGE_INPUT), "--output-directory", str(IMAGE_OUTPUT),
            "--user-directory", str(IMAGE_USER), "--temp-directory", str(IMAGE_TEMP)]
    if not face_detail:
        args.append("--disable-all-custom-nodes")
    args.extend(extra_args)
    # ComfyUI/tqdm emits Unicode progress glyphs.  On Windows the inherited
    # cp1252 console can raise inside tqdm after sampling finishes, preventing
    # the API from recording the output.  Keep this private renderer UTF-8.
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    env.update(OMP_NUM_THREADS="4", MKL_NUM_THREADS="4", OPENBLAS_NUM_THREADS="4")
    # Numba's in-tree cache probes can spin in tempfile on Windows when the
    # installation is read-only. Keep all generated cache files in our workspace.
    cache = ROOT / "work" / "runtime" / "numba_cache"
    cache.mkdir(parents=True, exist_ok=True)
    env["NUMBA_CACHE_DIR"] = str(cache)
    # Ultralytics otherwise tries to create its settings under the operator's
    # roaming profile during node import. Keep this isolated renderer's cache
    # and settings inside the auditable workspace runtime.
    yolo_config = IMAGE_RUNTIME / "ultralytics_config"
    yolo_config.mkdir(parents=True, exist_ok=True)
    env["YOLO_CONFIG_DIR"] = str(yolo_config)
    proc = None
    started = time.monotonic()
    state = "process_not_started"
    try:
        with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
            proc = subprocess.Popen(args, cwd=COMFY_ROOT, stdout=stdout, stderr=stderr, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        proc.startup_diagnostics = (args, stdout_path, stderr_path)
        if IMAGE_OWNER.is_file():
            owner = json.loads(IMAGE_OWNER.read_text(encoding="utf-8"))
            if owner.get("pid") == os.getpid():
                owner["backend_pid"] = proc.pid
                owner["backend_command"] = args
                owner["backend_logs"] = [str(stdout_path), str(stderr_path)]
                IMAGE_OWNER.write_text(json.dumps(owner, indent=2), encoding="utf-8")
        state = "alive_not_listening"
        deadline = started + startup_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                state = "process_exited"
                raise ImageRenderError("backend exited before readiness")
            thermal_guard.check_running_ceiling(print, "comfy-startup")
            try:
                _get_json(f"{API}/object_info", timeout=min(2, max(.1, deadline-time.monotonic())))
                proc.server_ready = True
                _backend_health(proc, args, stdout_path, stderr_path, "server_ready",
                                elapsed_seconds=round(time.monotonic()-started, 3))
                return proc
            except ImageRenderError:
                time.sleep(min(.5, max(0, deadline-time.monotonic())))
        # The loop's last probe can fail (or be clamped to a tiny timeout)
        # just as the server starts listening.  Close that race with exactly
        # one full-length probe before giving up; this is not a retry loop.
        if proc.poll() is not None:
            state = "process_exited"
            raise ImageRenderError("backend exited before readiness")
        thermal_guard.check_running_ceiling(print, "comfy-startup")
        try:
            _get_json(f"{API}/object_info", timeout=2)
        except ImageRenderError:
            raise ImageRenderError("startup deadline exceeded") from None
        proc.server_ready = True
        _backend_health(proc, args, stdout_path, stderr_path, "server_ready",
                        elapsed_seconds=round(time.monotonic()-started, 3),
                        ready_on_final_check=True)
        return proc
    except Exception as exc:
        record = _backend_health(proc, args, stdout_path, stderr_path, state,
                                 error=str(exc), elapsed_seconds=round(time.monotonic()-started, 3))
        try:
            _stop_owned_backend(proc)
        except Exception as cleanup:
            record["cleanup_error"] = str(cleanup)
            _backend_health(proc, args, stdout_path, stderr_path, "cleanup_failed",
                            error=str(exc), cleanup_error=str(cleanup))
        raise ImageRenderError(json.dumps(record, ensure_ascii=False)) from exc


def _stop_owned_backend(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    if os.name == "nt":
        check = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process -Filter 'ProcessId = {int(proc.pid)}' | Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=10)
        command = check.stdout.lower().replace("/", chr(92))
        verified = (not check.returncode and "main.py" in command
                    and str(COMFY_PYTHON).lower().replace("/", chr(92)) in command
                    and str(IMAGE_USER).lower().replace("/", chr(92)) in command)
        if not verified:
            # Win32_Process command-line queries can be denied while the
            # Popen handle remains ours.  Fall back to the executable path;
            # never accept a different executable or an unknown process.
            probe = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"$p=Get-Process -Id {int(proc.pid)} -ErrorAction SilentlyContinue; if($p){{$p.Path}}"],
                capture_output=True, text=True, timeout=10)
            exe = probe.stdout.strip().lower().replace("/", chr(92))
            expected = str(COMFY_PYTHON).lower().replace("/", chr(92))
            verified = bool(exe and exe == expected)
        if not verified:
            raise ImageRenderError(f"cannot verify owned backend command line for {proc.pid}; retaining owner")
    try:
        urllib.request.urlopen(urllib.request.Request(f"{API}/interrupt", data=b"{}",
                               headers={"Content-Type": "application/json"}, method="POST"), timeout=4).read()
    except Exception:
        pass
    try:
        urllib.request.urlopen(urllib.request.Request(
            f"{API}/free",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        ), timeout=10).read()
    except Exception:
        pass
    if proc.poll() is None:
        if os.name == "nt":
            # Windows: ComfyUI can leave child listeners; kill the whole tree.
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True, text=True, timeout=30,
            )
            # Some Windows installations deny taskkill even though this
            # process created the backend and still owns its Popen handle.
            # TerminateProcess through that exact handle is narrower and does
            # not require rediscovering or guessing a PID.  It is safe only
            # here, after the executable/command line ownership checks above.
            if result.returncode and proc.poll() is None:
                try:
                    proc.kill()
                except OSError as exc:
                    raise ImageRenderError(
                        f"cannot stop verified owned backend {proc.pid}: "
                        f"taskkill={result.stderr.strip()}; handle={exc}"
                    ) from exc
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired as exc:
                raise ImageRenderError(f"cannot stop owned backend {proc.pid}: {result.stderr}") from exc
        else:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
    # Wait until 8188 is actually free so the next still can claim it.
    for _ in range(60):
        if not _port_open():
            break
        time.sleep(0.5)
    if _port_open():
        raise ImageRenderError("port remains occupied after owned backend cleanup; no retry")


def _checkpoint_available(info: dict, model: str) -> bool:
    try:
        choices = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        return model in choices
    except Exception:
        return False


def _post_prompt(graph: dict) -> str:
    data = json.dumps({"prompt": graph, "client_id": "equal-shares-image-render"}).encode("utf-8")
    request = urllib.request.Request(f"{API}/prompt", data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # ComfyUI places the actionable node-validation reason in the HTTP
        # response body. Preserve a bounded copy so a recovery policy can fix
        # the actual bad node rather than retrying an opaque 400.
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:8000]
        except Exception:
            detail = "<unreadable HTTP error body>"
        raise ImageRenderError(f"ComfyUI rejected image graph: {exc}; detail={detail}") from exc
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
        raise ImageRenderError(f"ComfyUI rejected image graph: {exc}") from exc
    prompt_id = str(payload.get("prompt_id") or "")
    if not prompt_id:
        raise ImageRenderError(f"ComfyUI returned no prompt id: {payload}")
    return prompt_id


def _wait_for_outputs(prompt_id: str, proc: subprocess.Popen | None = None,
                      timeout_s: int = 900,
                      output_node_ids: set[str] | None = None) -> list[dict]:
    until, last_thermal = time.time() + timeout_s, 0.0
    last_poll_error = ""
    while time.time() < until:
        if proc is not None and proc.poll() is not None:
            raise ImageRenderError(
                f"owned ComfyUI exited while waiting for image output (rc={proc.returncode})"
            )
        if time.time() - last_thermal >= 15:
            thermal_guard.check_running_ceiling(lambda message: print(message, flush=True), "image-render")
            last_thermal = time.time()
        # 2026-09-24: a single slow /history response (8 s read timeout) while
        # the GPU was busy killed a job whose image was then written anyway.
        # Transport failures here are transient polling noise; retry them within
        # timeout_s.  Graph errors and backend exit still raise immediately.
        try:
            history = _get_json(f"{API}/history/{prompt_id}")
        except ImageRenderError as exc:
            last_poll_error = str(exc)
            print(f"history poll failed, retrying: {exc}", flush=True)
            time.sleep(2)
            continue
        try:
            item = history.get(prompt_id) or {}
            if item.get("status", {}).get("status_str") == "error" or item.get("status", {}).get("status") == "error":
                raise ImageRenderError(f"ComfyUI image graph failed: {item.get('status')}")
            outputs = item.get("outputs") or {}
            # Custom processing nodes can expose temporary UI previews alongside
            # the actual SaveImage deliverable. Never let those previews cross
            # the evidence boundary: only collect images from the graph's
            # explicit output node(s) when the caller supplies them.
            selected = (
                (node_id, node) for node_id, node in outputs.items()
                if output_node_ids is None or str(node_id) in output_node_ids
            )
            images = [image for _node_id, node in selected
                      for image in node.get("images", [])]
            if images:
                return images
        except ImageRenderError:
            raise
        except Exception:
            pass
        time.sleep(2)
    detail = f"; last /history poll error: {last_poll_error}" if last_poll_error else ""
    raise ImageRenderError(f"image graph timed out after {timeout_s} seconds{detail}")


_MODEL_LOADER_INPUTS = {"CheckpointLoaderSimple": "ckpt_name", "UNETLoader": "unet_name"}


def _node_order(node_id: str) -> tuple:
    return (0, int(node_id), "") if str(node_id).isdigit() else (1, 0, str(node_id))


def effective_settings(graph: dict) -> dict:
    """Read model and primary-pass sampling values from the graph actually built.

    build_graph overrides caller values (the profile's model always wins,
    realpro_flux pins euler/simple/cfg 1.0/denoise 1.0, t2i pins denoise 1.0),
    so argparse values are only what was requested. The primary pass is the
    lowest-numbered sampler node; hi-res and detailer passes come after it.
    A graph without a loader or sampler (liveportrait) records None.
    hires_fix is true only when a sampler refines a LatentUpscaleBy output;
    the flag is ignored outside t2i and by realpro_flux and alicemix_sd15.
    width/height predict the saved image: the EmptyLatentImage size, scaled
    the way ComfyUI's LatentUpscaleBy rounds latent pixels. Modes that start
    from an input image take its size, which the graph cannot know, so None;
    main() replaces both with the measured PNG size once outputs exist.
    """
    model = None
    for node_id in sorted(graph, key=_node_order):
        node = graph[node_id]
        key = _MODEL_LOADER_INPUTS.get(node.get("class_type"))
        if key:
            model = node.get("inputs", {}).get(key)
            break
    sampler_inputs: dict = {}
    for node_id in sorted(graph, key=_node_order):
        inputs = graph[node_id].get("inputs", {})
        if "sampler_name" in inputs:
            sampler_inputs = inputs
            break
    upscales = [
        graph[str(link[0])] for node in graph.values()
        if isinstance(link := node.get("inputs", {}).get("latent_image"), list)
        and "sampler_name" in node.get("inputs", {})
        and graph.get(str(link[0]), {}).get("class_type") == "LatentUpscaleBy"]
    width = height = None
    for node in graph.values():
        if node.get("class_type") == "EmptyLatentImage":
            # EmptyLatentImage allocates width // 8 latent pixels.
            latent_w, latent_h = int(node["inputs"]["width"]) // 8, int(node["inputs"]["height"]) // 8
            for upscale in upscales:
                scale = float(upscale["inputs"]["scale_by"])
                latent_w, latent_h = round(latent_w * scale), round(latent_h * scale)
            width, height = latent_w * 8, latent_h * 8
            break
    return {
        "model": model,
        "steps": sampler_inputs.get("steps"),
        "cfg": sampler_inputs.get("cfg"),
        "sampler": sampler_inputs.get("sampler_name"),
        "scheduler": sampler_inputs.get("scheduler"),
        "denoise": sampler_inputs.get("denoise"),
        "hires_fix": bool(upscales),
        "width": width, "height": height,
    }


def png_size(path: Path) -> tuple[int, int] | None:
    """Width/height from a PNG's IHDR chunk; None for anything else."""
    with Path(path).open("rb") as handle:
        head = handle.read(24)
    if len(head) < 24 or head[:8] != b"\x89PNG\r\n\x1a\n" or head[12:16] != b"IHDR":
        return None
    return int.from_bytes(head[16:20], "big"), int.from_bytes(head[20:24], "big")


def apply_measured_size(record: dict, verified: list[dict]) -> None:
    """Replace predicted width/height with the saved outputs' measured size.

    Left as predicted if no output could be measured or the outputs disagree.
    """
    sizes = {(item.get("width"), item.get("height")) for item in verified}
    if len(sizes) == 1:
        width, height = sizes.pop()
        if width is not None and height is not None:
            record["width"], record["height"] = width, height


def manifest(story: str, args: argparse.Namespace, graph: dict) -> dict:
    effective = effective_settings(graph)
    requested = {
        "model": args.model, "steps": args.steps, "cfg": args.cfg,
        "sampler": args.sampler, "scheduler": args.scheduler, "denoise": args.denoise,
        "hires_fix": args.hires_fix, "width": args.width, "height": args.height,
    }
    return {
        "created_at": _now(),
        "story": story, "mode": args.mode, "model_profile": args.model_profile, "prompt": args.prompt,
        "negative": args.negative, "model": effective["model"], "seed": args.seed,
        "width": effective["width"], "height": effective["height"], "steps": effective["steps"],
        "cfg": effective["cfg"], "sampler": effective["sampler"], "scheduler": effective["scheduler"],
        "denoise": effective["denoise"], "requested": requested,
        "reference": args.reference or None,
        "mask": args.mask or None, "identity_reference": args.identity_reference or None,
        "identity_weight": args.identity_weight, "pose_reference": args.pose_reference or None,
        "pose_strength": args.pose_strength,
        "pose_end_percent": args.pose_end_percent,
        "smile_strength": args.smile_strength,
        "mouth_open": args.mouth_open,
        "liveportrait_crop_factor": args.liveportrait_crop_factor,
        "hires_fix": effective["hires_fix"], "face_detail": args.face_detail,
        "status": "planned", "graph": graph,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--story", required=True)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--model-profile", choices=tuple(MODEL_PROFILES), default="realvisxl")
    parser.add_argument(
        "--mode",
        choices=("t2i", "i2i", "i2i_identity", "inpaint_identity", "inpaint_identity_pose",
                 "face_refine_identity", "liveportrait_expression",
                 "hand_crop_inpaint", "hand_detailer", "hand_refiner_sd15",
                 "hand_openpose_sdxl"),
        default="t2i",
    )
    parser.add_argument("--reference", help="ComfyUI input filename for i2i; no paths outside its input directory")
    parser.add_argument("--mask", help="ComfyUI input filename whose alpha channel defines the inpaint mask")
    parser.add_argument("--identity-reference", help="ComfyUI input filename cropped for identity conditioning")
    parser.add_argument("--identity-weight", type=float, default=0.85)
    parser.add_argument("--pose-reference", help="ComfyUI input filename for the target OpenPose map")
    parser.add_argument("--pose-strength", type=float, default=1.0)
    parser.add_argument("--pose-end-percent", type=float, default=0.92)
    parser.add_argument("--grow-mask-by", type=int, default=8,
                        help="VAEEncodeForInpaint mask grow in pixels")
    parser.add_argument("--use-latent-noise-mask", action="store_true",
                        help="Identity inpaint: VAEEncode+SetLatentNoiseMask instead of VAEEncodeForInpaint")
    parser.add_argument("--smile-strength", type=float, default=1.0)
    parser.add_argument("--mouth-open", type=float, default=0.0)
    parser.add_argument("--liveportrait-crop-factor", type=float, default=2.0)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    parser.add_argument("--cfg", type=float, default=6.0)
    parser.add_argument("--sampler", default="dpmpp_2m_sde")
    parser.add_argument("--scheduler", default="karras")
    parser.add_argument("--denoise", type=float, default=0.55)
    parser.add_argument("--no-hires-fix", dest="hires_fix", action="store_false",
                        help="Skip the automatic t2i second-pass refinement (faster, lower detail)")
    parser.set_defaults(hires_fix=True)
    parser.add_argument("--face-detail", action="store_true",
                        help="Opt in to the Impact Pack face repair pass for damaged or small faces")
    parser.add_argument('--lora-name')
    parser.add_argument('--lora-strength', type=float, default=0.5)
    parser.add_argument("--plan", action="store_true", help="Read-only graph validation; never load a checkpoint")
    parser.add_argument("--execute", action="store_true", help="Reserved for guarded owned-backend execution")
    parser.add_argument("--allow-model-load", action="store_true")
    parser.add_argument("--result-file", type=Path, help="Write this attempt's structured receipt; must not exist")
    parser.add_argument("--attempt-id", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.plan == args.execute:
        raise ImageRenderError("choose exactly one of --plan or --execute")
    if args.execute and not args.allow_model_load:
        raise ImageRenderError("--execute requires explicit --allow-model-load")
    if args.result_file and args.result_file.exists():
        raise ImageRenderError("result-file already exists; use a new attempt path")
    story = _safe_segment(args.story, "story")
    attempt = _safe_segment(args.attempt_id or uuid.uuid4().hex, "attempt")
    prefix = f"stories/{story}/renders/{attempt}"
    model = MODEL_PROFILES[args.model_profile]["model"]
    graph = build_graph(mode=args.mode, prompt=args.prompt, negative=args.negative,
                        model=model, seed=args.seed, width=args.width,
                        height=args.height, steps=args.steps, cfg=args.cfg,
                        sampler=args.sampler, scheduler=args.scheduler,
                        denoise=args.denoise, prefix=prefix, reference_name=args.reference,
                        hires_fix=args.hires_fix, face_detail=args.face_detail,
                         profile=args.model_profile, lora_name=args.lora_name,
                         lora_strength=args.lora_strength, mask_name=args.mask,
                         identity_name=args.identity_reference,
                         identity_weight=args.identity_weight,
                         pose_name=args.pose_reference, pose_strength=args.pose_strength,
                         pose_end_percent=args.pose_end_percent,
            grow_mask_by=args.grow_mask_by,
                         smile_strength=args.smile_strength,
                         mouth_open=args.mouth_open,
                         liveportrait_crop_factor=args.liveportrait_crop_factor,
                         use_latent_noise_mask=bool(args.use_latent_noise_mask))
    if args.plan:
        info = object_info()
        validate_nodes(info, args.mode, profile=args.model_profile, face_detail=args.face_detail)
        print(json.dumps(manifest(story, args, graph), indent=2, ensure_ascii=False))
        return 0
    preflight_execute()
    if args.lora_name:
        assert_configured_model_visible(args.lora_name, 'loras')
    if args.mode in {"i2i_identity", "inpaint_identity", "inpaint_identity_pose", "face_refine_identity"}:
        assert_configured_model_visible(IPADAPTER_SDXL_FACE, "ipadapter")
        assert_configured_model_visible(CLIP_VISION_H, "clip_vision")
        if args.mode == "inpaint_identity_pose":
            assert_configured_model_visible(CONTROLNET_UNION_SDXL, "controlnet")
    # Fail fast on misconfigured extra_model_paths before booting Comfy.
    if args.mode == "liveportrait_expression":
        for asset in (
            "appearance_feature_extractor.safetensors",
            "motion_extractor.safetensors",
            "warping_module.safetensors",
            "spade_generator.safetensors",
            "stitching_retargeting_module.safetensors",
        ):
            assert_configured_model_visible(asset, "liveportrait")
        assert_configured_model_visible("face_yolov8n.pt", "ultralytics")
    elif args.mode == "hand_detailer":
        assert_configured_model_visible(HAND_DETAIL_MODEL, "ultralytics")
        assert_configured_model_visible(model, "checkpoints")
    elif args.mode == "hand_refiner_sd15":
        assert_configured_model_visible(HAND_REFINER_CONTROLNET, "controlnet")
        assert_configured_model_visible(model, "checkpoints")
    elif args.mode == "hand_openpose_sdxl":
        assert_configured_model_visible(CONTROLNET_UNION_SDXL, "controlnet")
        assert_configured_model_visible(model, "checkpoints")
    elif args.model_profile == "realpro_flux":
        assert_configured_model_visible(model, "diffusion_models")
    else:
        assert_configured_model_visible(model, "checkpoints")
    _write_owner()
    proc: subprocess.Popen | None = None
    try:
        proc = _start_owned_backend(
            face_detail=args.face_detail or args.mode in {
                "i2i_identity", "inpaint_identity", "inpaint_identity_pose", "face_refine_identity",
                "liveportrait_expression", "hand_crop_inpaint", "hand_detailer",
                "hand_refiner_sd15", "hand_openpose_sdxl"})
        info = object_info()
        validate_nodes(info, args.mode, profile=args.model_profile, face_detail=args.face_detail)
        if args.mode == "liveportrait_expression":
            available = None
        elif args.model_profile == "realpro_flux":
            available = info["UNETLoader"]["input"]["required"]["unet_name"][0]
        else:
            available = info["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
        if available is not None and model not in available:
            raise ImageRenderError(f"model not visible to owned backend: {model}")
        if args.lora_name:
            choices = info.get('LoraLoader', {}).get('input', {}).get('required', {}).get('lora_name', [[]])[0]
            if args.lora_name not in choices:
                raise ImageRenderError(f'LoRA not visible to owned backend: {args.lora_name}')
        if args.mode in {"i2i_identity", "inpaint_identity", "inpaint_identity_pose", "face_refine_identity"}:
            ip_choices = info["IPAdapterModelLoader"]["input"]["required"]["ipadapter_file"][0]
            clip_choices = info["CLIPVisionLoader"]["input"]["required"]["clip_name"][0]
            if IPADAPTER_SDXL_FACE not in ip_choices:
                raise ImageRenderError(
                    f"identity model not visible to owned backend: {IPADAPTER_SDXL_FACE}")
            if CLIP_VISION_H not in clip_choices:
                raise ImageRenderError(
                    f"CLIP vision model not visible to owned backend: {CLIP_VISION_H}")
            if args.mode == "inpaint_identity_pose":
                control_choices = info["ControlNetLoader"]["input"]["required"]["control_net_name"][0]
                if CONTROLNET_UNION_SDXL not in control_choices:
                    raise ImageRenderError(
                        f"pose ControlNet not visible to owned backend: {CONTROLNET_UNION_SDXL}"
                    )
        if args.mode == "hand_detailer":
            detector_choices = info["UltralyticsDetectorProvider"]["input"]["required"]["model_name"][0]
            if HAND_DETAIL_MODEL not in detector_choices:
                raise ImageRenderError(
                    f"hand detector not visible to owned backend: {HAND_DETAIL_MODEL}"
                )
        if args.mode == "hand_refiner_sd15":
            control_choices = info["ControlNetLoader"]["input"]["required"][
                "control_net_name"
            ][0]
            if HAND_REFINER_CONTROLNET not in control_choices:
                raise ImageRenderError(
                    "hand-refiner ControlNet not visible to owned backend: "
                    f"{HAND_REFINER_CONTROLNET}"
                )
        if args.mode == "hand_openpose_sdxl":
            control_choices = info["ControlNetLoader"]["input"]["required"][
                "control_net_name"
            ][0]
            if CONTROLNET_UNION_SDXL not in control_choices:
                raise ImageRenderError(
                    "open-palm ControlNet not visible to owned backend: "
                    f"{CONTROLNET_UNION_SDXL}"
                )
        prompt_id = _post_prompt(graph)
        save_node_ids = {
            str(node_id) for node_id, node in graph.items()
            if node.get("class_type") == "SaveImage"
        }
        if not save_node_ids:
            raise ImageRenderError("image graph has no explicit SaveImage evidence node")
        images = _wait_for_outputs(
            prompt_id, proc, output_node_ids=save_node_ids
        )
        record = manifest(story, args, graph)
        record.update({"status": "complete", "prompt_id": prompt_id, "outputs": images})
        verified = []
        for item in images:
            path = (IMAGE_OUTPUT / item.get("subfolder", "") / item["filename"]).resolve()
            relative = path.relative_to(IMAGE_OUTPUT.resolve()).as_posix()
            if not relative.startswith(prefix + "_") or not path.is_file():
                raise ImageRenderError("output does not belong to this attempt")
            with path.open("rb") as handle:
                digest = hashlib.file_digest(handle, "sha256").hexdigest()
            size = png_size(path)
            verified.append({"path": str(path), "sha256": digest,
                             "width": size[0] if size else None,
                             "height": size[1] if size else None})
        record.update(attempt_id=attempt, verified_outputs=verified)
        apply_measured_size(record, verified)
        dest = story_dir(story) / "manifests"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"image_{prompt_id}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
        if args.result_file:
            args.result_file.parent.mkdir(parents=True, exist_ok=True)
            with args.result_file.open("x", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2)
        print(json.dumps(record, indent=2, ensure_ascii=False))
        return 0
    finally:
        _stop_owned_backend(proc)
        _release_owner()
        thermal_guard.wait_after_render(lambda message: print(message, flush=True))


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ImageRenderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
