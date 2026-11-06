#!/usr/bin/env python3
"""Pinned ComfyUI API templates for reference-video motion transfer
(AnimateDiff-SDXL + union-openpose ControlNet + IP-Adapter), and the builder
that fills them.

The graphs are the configuration the 2026-09-25/26 proof-of-concept runs
converged on (CHANGELOG 2026-09-25t/u/v, 2026-09-26a/g): DWPose with face
keypoints off and xinsir stick scaling, RealVisXL 5 + ``mm_sdxl_v10_beta``
in 16-frame contexts with overlap 4, union-promax ``openpose`` at 0.8,
PLUS FACE IP-Adapter on a tight face crop masked to the character's region
per frame, and an Impact video face-detail pass at denoise 0.5 whose adapter
is FaceID Plus V2.  Every value that is not a pinned setting is a
``"{{PLACEHOLDER}}"`` token in the JSON; ``build_stage1`` / ``build_stage2``
substitute them (whole-token JSON replacement, so numbers stay numbers) and
refuse to return a graph with any token left.

Two stages, one owned backend:

1. ``stage1_pose``: reference clip → DWPose maps + ``SavePoseKpsAsJsonFile``
   (the keypoints ``motion_transfer_masks`` turns into per-frame masks).
2. ``stage2_render``: the render, reading the per-frame masks back through
   ``VHS_LoadImagesPath`` → ``ImageToMask``.  When the mask module's face rule
   is ``union_mask``, node 42 becomes ``ImpactSegsAndMask`` over the union
   mask instead of the ordered filter.

Templates live in ``local_agent/graphs/`` and are pinned by sha256 in
``TEMPLATE_SHA256``; ``test_motion_transfer_graph`` fails if they drift.
No GPU, no ComfyUI: pure text.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GRAPHS = HERE / "graphs"
STAGE1 = "motion_transfer_animatediff_stage1_pose_api.json"
STAGE2 = "motion_transfer_animatediff_stage2_render_api.json"

# Pinned settings that are baked into the templates (informational; the
# templates are the truth, and this dict is asserted against them in tests).
PINNED: dict[str, Any] = {
    "checkpoint": "RealVisXL_V5.0_fp16.safetensors",
    "motion_module": "mm_sdxl_v10_beta.ckpt",
    "beta_schedule": "linear (AnimateDiff-SDXL)",
    "context": {"length": 16, "overlap": 4, "fuse": "pyramid"},
    "controlnet": "controlnet-union-sdxl-1.0-promax.safetensors",
    "controlnet_type": "openpose",
    "controlnet_strength": 0.8,
    "dwpose": {"detect_face": "disable", "detect_hand": "enable", "scale_stick_for_xinsr_cn": "enable",
               "resolution": 512},
    "ipadapter_main": {"preset": "PLUS FACE (portraits)", "weight": 0.8, "weight_type": "linear",
                       "embeds_scaling": "V only", "mask": "per-frame batch"},
    "ipadapter_detail": {"preset": "FACEID PLUS V2", "lora_strength": 0.6, "weight": 0.8,
                         "weight_faceidv2": 1.0, "provider": "CPU"},
    "face_detail": {"detector": "bbox/face_yolov8m.pt", "guide_size": 384, "max_size": 512,
                    "feather": 8, "noise_mask_feather": 20, "crop_factor": 3.0},
    "sampler": {"name": "euler", "scheduler": "normal", "denoise": 1.0},
}

# Defaults an operator may override per job.
DEFAULTS: dict[str, Any] = {
    "force_fps": 8,
    "frame_cap": 24,          # one prompt; 24 frames measured at ~14.7 GB peak (26a/26g)
    "width": 768,
    "height": 448,
    "steps": 20,
    "cfg": 6.0,
    "fd_denoise": 0.5,
    "negative": ("cartoon, anime, illustration, deformed, extra limbs, extra fingers, bad hands, "
                 "blurry, watermark, text, logo, duplicate person"),
    "fd_positive": ("photoreal close-up of the character's face, the same person as the reference "
                    "photo, natural skin texture, natural eyes"),
    "fd_negative": ("different person, cartoon, deformed face, asymmetric eyes, blurry, "
                    "watermark, text"),
}

TEMPLATE_SHA256: dict[str, str] = {
    STAGE1: "02bea262ec29be325114a627aae2a89a3c6f2b4460232728e05105fd2edf63a5",
    STAGE2: "0836f376fe7325a9ce7069046d6ca45549fc5e597fc652d084363de0ce8c62ba",
}

STAGE1_OUTPUT_NODES = frozenset({"3", "4"})       # SaveImage nodes; node 5 writes the JSON
STAGE2_OUTPUT_NODES = frozenset({"24", "48"})     # undetailed and detailed frames
STAGE2_VIDEO_NODES = frozenset({"25", "49"})


class TemplateError(ValueError):
    pass


def template_path(name: str) -> Path:
    return GRAPHS / name


def template_text(name: str) -> str:
    return template_path(name).read_text(encoding="utf-8")


def template_sha256(name: str) -> str:
    return hashlib.sha256(template_path(name).read_bytes()).hexdigest()


def placeholders(name: str) -> set[str]:
    import re
    return set(re.findall(r"\{\{([A-Z_]+)\}\}", template_text(name)))


def _fill(name: str, values: dict[str, Any]) -> dict[str, Any]:
    """Whole-token replacement first (``"{{KEY}}"`` → the JSON value, so
    numbers and booleans keep their type); then string values may also
    appear inside a longer string (``"{{PREFIX}}/pose"``), where the
    JSON-escaped text is spliced in."""
    text = template_text(name)
    for key, value in values.items():
        token = '"{{' + key + '}}"'
        text = text.replace(token, json.dumps(value))
    for key, value in values.items():
        if isinstance(value, str):
            text = text.replace("{{" + key + "}}", json.dumps(value)[1:-1])
    if "{{" in text:
        import re
        left = sorted(set(re.findall(r"\{\{([A-Z_]+)\}\}", text)))
        raise TemplateError(f"{name}: unfilled placeholders {left}")
    return json.loads(text)


def _check_common(*, reference_video: str, frame_cap: int, skip_first: int, force_fps: int,
                  prefix: str) -> None:
    if not str(reference_video).strip():
        raise TemplateError("reference_video is required")
    if not 1 <= int(frame_cap) <= 64:
        raise TemplateError("frame_cap must be 1..64 (one prompt; 24 is the measured window)")
    if int(skip_first) < 0:
        raise TemplateError("skip_first must be >= 0")
    if not 1 <= int(force_fps) <= 30:
        raise TemplateError("force_fps must be 1..30")
    if not prefix or "/" not in prefix or ".." in prefix or prefix.startswith("/"):
        raise TemplateError("prefix must be '<subfolder>/<name>' under the owned output root")


def build_stage1(*, reference_video: str, frame_cap: int, skip_first: int, force_fps: int,
                 prefix: str) -> dict[str, Any]:
    _check_common(reference_video=reference_video, frame_cap=frame_cap, skip_first=skip_first,
                  force_fps=force_fps, prefix=prefix)
    return _fill(STAGE1, {
        "REFERENCE_VIDEO": str(reference_video), "FORCE_FPS": int(force_fps),
        "FRAME_CAP": int(frame_cap), "SKIP_FIRST": int(skip_first), "PREFIX": prefix,
    })


def build_stage2(*, reference_video: str, frame_cap: int, skip_first: int, force_fps: int,
                 width: int, height: int, character_face_image: str, masks_dir: str,
                 positive: str, negative: str | None, seed: int, prefix: str,
                 face_rule: dict[str, Any], union_mask_dir: str | None = None,
                 steps: int | None = None, cfg: float | None = None,
                 fd_positive: str | None = None, fd_negative: str | None = None,
                 fd_denoise: float | None = None) -> dict[str, Any]:
    _check_common(reference_video=reference_video, frame_cap=frame_cap, skip_first=skip_first,
                  force_fps=force_fps, prefix=prefix)
    if int(width) % 8 or int(height) % 8 or int(width) < 256 or int(height) < 256:
        raise TemplateError("width and height must be multiples of 8 and at least 256")
    if not str(character_face_image).strip() or "/" in character_face_image or "\\" in character_face_image:
        raise TemplateError("character_face_image must be a file name in the owned input dir")
    if not str(masks_dir).strip():
        raise TemplateError("masks_dir is required")
    if not str(positive).strip():
        raise TemplateError("positive prompt is required")
    if not 1 <= int(seed) <= 2**63 - 1:
        raise TemplateError("seed must be a positive 64-bit integer")
    steps = int(DEFAULTS["steps"] if steps is None else steps)
    cfg = float(DEFAULTS["cfg"] if cfg is None else cfg)
    fd_denoise = float(DEFAULTS["fd_denoise"] if fd_denoise is None else fd_denoise)
    if not 1 <= steps <= 60 or not 1.0 <= cfg <= 20.0 or not 0.0 <= fd_denoise <= 1.0:
        raise TemplateError("steps 1..60, cfg 1..20, fd_denoise 0..1")
    mode = str(face_rule.get("mode") or "")
    if mode == "ordered":
        target = str(face_rule.get("target") or "")
        if target not in {"x1", "y1", "x2", "y2", "area(=w*h)", "area", "width", "height"}:
            raise TemplateError(f"face_rule.target {target!r} is not an ImpactSEGSOrderedFilter target")
        if target == "area":
            target = "area(=w*h)"
        face_values = {"FACE_TARGET": target, "FACE_ORDER": bool(face_rule.get("order")),
                       "FACE_TAKE": int(face_rule.get("take_count") or 1)}
    elif mode == "union_mask":
        if not union_mask_dir:
            raise TemplateError("union_mask_dir is required when face_rule.mode == 'union_mask'")
        face_values = {"FACE_TARGET": "x1", "FACE_ORDER": False, "FACE_TAKE": 1}
    else:
        raise TemplateError("face_rule.mode must be 'ordered' or 'union_mask'")
    graph = _fill(STAGE2, {
        "REFERENCE_VIDEO": str(reference_video), "FORCE_FPS": int(force_fps),
        "FRAME_CAP": int(frame_cap), "SKIP_FIRST": int(skip_first), "PREFIX": prefix,
        "WIDTH": int(width), "HEIGHT": int(height),
        "CHARACTER_FACE_IMAGE": str(character_face_image), "MASKS_DIR": str(masks_dir),
        "POSITIVE": str(positive), "NEGATIVE": str(negative or DEFAULTS["negative"]),
        "SEED": int(seed), "STEPS": steps, "CFG": cfg,
        "FD_POSITIVE": str(fd_positive or DEFAULTS["fd_positive"]),
        "FD_NEGATIVE": str(fd_negative or DEFAULTS["fd_negative"]),
        "FD_DENOISE": fd_denoise, **face_values,
    })
    if mode == "union_mask":
        # Documented substitution: the ordered filter cannot isolate this
        # character, so the SEGS are intersected with the union body mask.
        graph["28"] = {"class_type": "VHS_LoadImagesPath",
                       "inputs": {"directory": str(union_mask_dir), "image_load_cap": 1,
                                  "skip_first_images": 0, "select_every_nth": 1}}
        graph["29"] = {"class_type": "ImageToMask", "inputs": {"image": ["28", 0], "channel": "red"}}
        graph["42"] = {"class_type": "ImpactSegsAndMask",
                       "inputs": {"segs": ["41", 0], "mask": ["29", 0]}}
    return graph


def validate_graph(graph: dict, info: dict) -> list[str]:
    """Every class must exist in live object_info and every input name must
    be declared (required or optional); combo values must be choices.  Same
    check the proof-of-concept runner used, so an unknown input fails here
    and not as an opaque HTTP 400."""
    problems: list[str] = []
    for node_id, node in graph.items():
        spec = info.get(node["class_type"])
        if not spec:
            problems.append(f"node {node_id}: class {node['class_type']} not in object_info")
            continue
        inputs = spec.get("input") or {}
        declared = set((inputs.get("required") or {}).keys()) | set((inputs.get("optional") or {}).keys())
        for name in node["inputs"]:
            if name not in declared:
                problems.append(f"node {node_id} ({node['class_type']}): unknown input {name!r}; "
                                f"declared={sorted(declared)}")
        for name, spec_in in (inputs.get("required") or {}).items():
            if name not in node["inputs"] and isinstance(spec_in, list) and spec_in and \
                    isinstance(spec_in[0], str) and spec_in[0] in (
                        "MODEL", "CLIP", "VAE", "IMAGE", "LATENT", "CONDITIONING", "CONTROL_NET",
                        "IPADAPTER", "CONTEXT_OPTIONS", "SEGS", "MASK", "BASIC_PIPE", "BBOX_DETECTOR",
                        "POSE_KEYPOINT"):
                problems.append(f"node {node_id} ({node['class_type']}): required link {name!r} missing")
        for name, value in node["inputs"].items():
            for section in ("required", "optional"):
                spec_in = (inputs.get(section) or {}).get(name)
                if not spec_in or not isinstance(value, str):
                    continue
                choices = None
                if isinstance(spec_in[0], list):
                    choices = spec_in[0]
                elif spec_in[0] == "COMBO" and len(spec_in) > 1 and isinstance(spec_in[1], dict):
                    choices = spec_in[1].get("options")
                if choices is not None and value not in choices:
                    problems.append(f"node {node_id} ({node['class_type']}): {name}={value!r} "
                                    f"not in choices {list(choices)[:12]}")
    return problems


def node_classes(graph: dict) -> list[str]:
    return sorted({str(n.get("class_type")) for n in graph.values()})
