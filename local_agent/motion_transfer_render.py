#!/usr/bin/env python3
"""render_video_from_reference: recast a reference clip's motion with a character still.

Background job runner + pinned graph template (2026-09-26, CHANGELOG 2026-09-26 entry for
this build). The tool wrapper in tools.py validates the request with ``prepare_job``,
passes the GPU gate, and spawns ``python motion_transfer_render.py --job-dir DIR``; this
process then owns the private ComfyUI backend through work/image_render.py's lifecycle
(preflight, owner file, one backend, thermal guard, always stop + release).

Approach and settings are the ones measured in CHANGELOG 2026-09-25t/u/v and
2026-09-26a/g:
- AnimateDiff-SDXL (RealVisXL + mm_sdxl_v10_beta), 16-frame context, overlap 4, with
  ComfyUI-Advanced-ControlNet for multi-window clips;
- union-promax ControlNet ``openpose`` on DWPose body + hands with **face keypoints off**
  and xinsir-scaled sticks (face + hand keypoints together flip the scene upside down);
- IP-Adapter PLUS FACE on an automatic square crop of the character's face, masked to the
  target person's region when other people share the frame;
- an Impact Pack video face-detail pass (denoise 0.5) on the target face through FaceID
  Plus V2 (PLUS FACE when the still has no detectable face or FaceID is not installed).

Outputs land under outputs/stories/_comfy_output/motion_transfer/<job_id>/ (ComfyUI) and
outputs/motion_transfer/<job_id>/ (job.json, status.json, graph.json, manifest.json,
runner.log, face crop, mask). Nothing is accepted automatically: the manifest carries file
evidence and a machine identity score; likeness and motion acceptance are the operator's.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "work"))

import motion_transfer  # noqa: E402  (probe/validation helpers of the planner)

JOBS_ROOT = ROOT / "outputs" / "motion_transfer"
COMFY_SUBDIR = "motion_transfer"
FACES_HELPER = HERE / "motion_transfer_faces.py"
FORBIDDEN_TREE = (ROOT / "outputs" / "equal_shares").resolve()

TEMPLATE_VERSION = "animatediff_sdxl_pose_ipadapter_faceid_v1"
CHECKPOINT = "RealVisXL_V5.0_fp16.safetensors"
MOTION_MODULE = "mm_sdxl_v10_beta.ckpt"
BETA_SCHEDULE = "linear (AnimateDiff-SDXL)"
CONTROLNET = "controlnet-union-sdxl-1.0-promax.safetensors"
CN_STRENGTH = 0.8
STEPS, CFG, SAMPLER, SCHEDULER = 20, 6.0, "euler", "normal"
CONTEXT_LENGTH, CONTEXT_OVERLAP = 16, 4
IPA_WEIGHT = 0.8
FACE_DETECTOR = "bbox/face_yolov8m.pt"
FD_DENOISE, FD_GUIDE, FD_MAX = 0.5, 384, 512
FACEID_LORA, FACEID_V2 = 0.6, 1.0
FACEID_FILES = (("ipadapter", "ip-adapter-faceid-plusv2_sdxl.bin"),
                ("loras", "ip-adapter-faceid-plusv2_sdxl_lora.safetensors"))
INSIGHTFACE_PACK = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\models\insightface\models\buffalo_l")
SIZE_LANDSCAPE, SIZE_PORTRAIT = (768, 448), (448, 768)
MEASURED_SIZES = {SIZE_LANDSCAPE}
DEFAULT_FPS = 8
MIN_FPS, MAX_FPS = 4, 12
MIN_FRAMES = 8
# Longest clip rendered end-to-end through this tool with file evidence. Raise it only
# after a longer run has been measured (time, peak VRAM, frame count, visual check).
MAX_FRAMES = 64
TARGETS = ("auto", "largest", "left", "right", "center")
TRACK_SAMPLES = 8
DEFAULT_NEGATIVE = ("cartoon, anime, illustration, deformed, extra limbs, extra fingers, bad hands, "
                    "blurry, watermark, text, logo, duplicate person")
FD_POSITIVE = "photoreal close-up of a face, natural skin texture, natural eyes, sharp detail"
FD_NEGATIVE = "cartoon, deformed face, asymmetric eyes, blurry, watermark, text"


class RenderRequestError(ValueError):
    """The request cannot become a job (bad input, over a limit, missing attestation)."""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _under(path: Path, tree: Path) -> bool:
    try:
        path.resolve().relative_to(tree)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------------------
# request -> job spec (pure except for probing the two input files)
# ---------------------------------------------------------------------------------------

def output_size(width: int, height: int) -> tuple[int, int]:
    return SIZE_PORTRAIT if height > width else SIZE_LANDSCAPE


def plan_frames(duration_s: float, start_s: float, fps: float, max_seconds: float | None) -> int:
    """Frames the loader will really deliver.

    Up to the clip's end, keep a quarter-frame margin (the loader may stop one short);
    a max_seconds cut well inside the clip is exact.
    """
    remaining = max(0.0, duration_s - start_s)
    if max_seconds is not None and max_seconds * fps <= remaining * fps - 1.0:
        return int(math.floor(max_seconds * fps + 1e-9))
    return int(math.floor(remaining * fps - 0.25))


def faceid_installed() -> dict:
    import image_render
    found = {name: bool(image_render.model_file_on_configured_paths(name, folder))
             for folder, name in FACEID_FILES}
    found["buffalo_l"] = (INSIGHTFACE_PACK / "w600k_r50.onnx").is_file()
    found["installed"] = all(found.values())
    return found


def prepare_request(args: dict) -> dict:
    """Validate a tool call and return the job spec (no file is written here)."""
    if args.get("likeness_attestation") is not True:
        raise RenderRequestError(
            "likeness_attestation must be true: confirm the character is fictional or a person "
            "who consented, and that the output will not put a real, identifiable person's "
            "likeness into sexual content")
    try:
        video = motion_transfer._validated_path(args.get("reference_video"), motion_transfer.VIDEO_EXTS,
                                                "reference_video")
        still = motion_transfer._validated_path(args.get("character_image"), motion_transfer.IMAGE_EXTS,
                                                "character_image")
    except motion_transfer.PlanError as exc:
        raise RenderRequestError(str(exc)) from exc
    for p in (video, still):
        if _under(p, FORBIDDEN_TREE):
            raise RenderRequestError(f"refusing input under outputs/equal_shares: {p}")
    prompt = str(args.get("prompt") or "").strip()
    if len(prompt) < 12:
        raise RenderRequestError("prompt is required: describe the character and the scene (12+ characters)")
    negative = str(args.get("negative") or DEFAULT_NEGATIVE).strip()
    face_prompt = str(args.get("face_prompt") or FD_POSITIVE).strip()
    try:
        seed = int(args.get("seed", 20260925))
        fps = float(args.get("target_fps", DEFAULT_FPS))
        start_s = float(args.get("start_seconds", 0) or 0)
        max_s = args.get("max_seconds")
        max_s = float(max_s) if max_s not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise RenderRequestError(f"numeric parameter invalid: {exc}") from exc
    if not 1 <= seed <= 2**63 - 1:
        raise RenderRequestError("seed must be a positive 64-bit integer")
    if not MIN_FPS <= fps <= MAX_FPS:
        raise RenderRequestError(f"target_fps must be {MIN_FPS}-{MAX_FPS}")
    if start_s < 0 or (max_s is not None and max_s <= 0):
        raise RenderRequestError("start_seconds must be >= 0 and max_seconds > 0")
    target = str(args.get("target") or "auto").strip().lower()
    if target not in TARGETS:
        raise RenderRequestError(f"target must be one of {', '.join(TARGETS)}")
    face_detail = bool(args.get("face_detail", True))

    vinfo = motion_transfer.probe_video(video)
    sinfo = motion_transfer.probe_image(still)
    if not vinfo.get("duration_s") or not vinfo.get("width"):
        raise RenderRequestError("reference_video has no readable duration/size")
    if start_s >= vinfo["duration_s"]:
        raise RenderRequestError(f"start_seconds {start_s} is past the clip's end ({vinfo['duration_s']} s)")
    frames = plan_frames(vinfo["duration_s"], start_s, fps, max_s)
    if frames < MIN_FRAMES:
        raise RenderRequestError(f"only {frames} frames at {fps} fps; need at least {MIN_FRAMES}")
    if frames > MAX_FRAMES:
        seconds = MAX_FRAMES / fps
        raise RenderRequestError(
            f"{frames} frames requested; this tool is validated up to {MAX_FRAMES} frames "
            f"({seconds:.1f} s at {fps:g} fps). Pass max_seconds <= {seconds:.1f} (and start_seconds "
            "to choose the section); longer single renders need a measured longer run first")
    width, height = output_size(vinfo["width"], vinfo["height"])
    windows = 1 if frames <= CONTEXT_LENGTH else \
        1 + math.ceil((frames - CONTEXT_LENGTH) / (CONTEXT_LENGTH - CONTEXT_OVERLAP))
    return {
        "template_version": TEMPLATE_VERSION,
        "reference_video": vinfo, "character_image": sinfo,
        "prompt": prompt, "negative": negative, "face_prompt": face_prompt, "seed": seed,
        "target_fps": fps, "start_seconds": start_s, "skip_frames": int(round(start_s * fps)),
        "frames": frames, "windows": windows, "width": width, "height": height,
        "size_measured": (width, height) in MEASURED_SIZES,
        "target": target, "face_detail": face_detail,
        "likeness_attestation": True,
    }


def record_launch(job_dir: Path, pid: int) -> None:
    """Store the spawned runner's pid while the job is still queued (the runner then owns status)."""
    path = Path(job_dir) / "status.json"
    status = json.loads(path.read_text(encoding="utf-8"))
    if status.get("state") == "queued" and not status.get("pid"):
        status.update(pid=int(pid), launched_at=_now())
        _write_json(path, status)


def new_job(spec: dict) -> tuple[str, Path]:
    job_id = time.strftime("mtr_%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    job_dir = JOBS_ROOT / job_id
    job_dir.mkdir(parents=True, exist_ok=False)
    _write_json(job_dir / "job.json", dict(spec, job_id=job_id, created_at=_now()))
    _write_json(job_dir / "status.json", {"job_id": job_id, "state": "queued", "updated_at": _now()})
    return job_id, job_dir


# ---------------------------------------------------------------------------------------
# target person: who in the reference gets the character's identity, and where they stand
# ---------------------------------------------------------------------------------------

def map_x(x: float, src_w: int, src_h: int, out_w: int, out_h: int) -> float:
    """Normalised source x -> normalised output x under a centre crop to the output aspect."""
    src_aspect, out_aspect = src_w / src_h, out_w / out_h
    if src_aspect <= out_aspect:
        return x
    visible = out_aspect / src_aspect
    return (x - (1.0 - visible) / 2.0) / visible


def choose_target(frames: list[list[list[float]]], target: str) -> dict:
    """Pick and follow one face across sampled frames; derive its horizontal band.

    ``frames``: per sampled frame, faces as normalised [x1, y1, x2, y2, score].
    Returns people (max faces in a frame), rank (target's left-to-right index where
    all people are visible), and band [lo, hi] in source-normalised x: the part of the
    frame closer to the target than to its neighbours (median over frames), or None
    for a one-person clip.
    """
    seen = [f for f in frames if f]
    if not seen:
        return {"people": 0, "rank": 0, "band": None, "reason": "no face in any sampled frame"}
    people = max(len(f) for f in seen)
    centre = lambda b: (b[0] + b[2]) / 2.0  # noqa: E731
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])  # noqa: E731
    first = max(seen, key=len)
    if target == "left":
        pick = min(first, key=centre)
    elif target == "right":
        pick = max(first, key=centre)
    elif target == "center":
        pick = min(first, key=lambda b: abs(centre(b) - 0.5))
    else:  # auto / largest
        pick = max(first, key=area)
    track, prev = [], centre(pick)
    los, his, ranks = [], [], []
    for faces in seen:
        cur = min(faces, key=lambda b: abs(centre(b) - prev))
        prev = centre(cur)
        track.append(round(prev, 4))
        others = sorted(centre(b) for b in faces if b is not cur)
        left = [c for c in others if c < prev]
        right = [c for c in others if c > prev]
        los.append((prev + left[-1]) / 2.0 if left else 0.0)
        his.append((prev + right[0]) / 2.0 if right else 1.0)
        if len(faces) == people:
            ranks.append(sorted(faces, key=centre).index(cur))
    rank = statistics.mode(ranks) if ranks else 0
    if people <= 1:
        return {"people": people, "rank": 0, "band": None, "track": track}
    lo, hi = statistics.median(los), statistics.median(his)
    if hi - lo < 0.25:  # never a sliver: widen symmetrically around the target
        mid = statistics.median(track)
        lo, hi = max(0.0, mid - 0.125), min(1.0, mid + 0.125)
    return {"people": people, "rank": int(rank), "band": [round(lo, 4), round(hi, 4)], "track": track}


def band_to_pixels(band: list[float] | None, spec: dict) -> list[int] | None:
    if not band:
        return None
    v = spec["reference_video"]
    w = spec["width"]
    lo = min(max(map_x(band[0], v["width"], v["height"], w, spec["height"]), 0.0), 1.0)
    hi = min(max(map_x(band[1], v["width"], v["height"], w, spec["height"]), 0.0), 1.0)
    return [int(round(lo * w)), int(round(hi * w))]


# ---------------------------------------------------------------------------------------
# the pinned graph
# ---------------------------------------------------------------------------------------

def build_graph(spec: dict, inputs: dict, prefix: str) -> tuple[dict, str]:
    """Return (ComfyUI API graph, id of the node whose images mark completion).

    ``inputs``: face_image (file in the owned input dir), mask_image (file or None),
    face_found (bool), faceid (bool), people (int), rank (int).
    """
    frames, fps = spec["frames"], spec["target_fps"]
    g: dict[str, dict] = {
        "1": {"class_type": "VHS_LoadVideoPath",
              "inputs": {"video": spec["reference_video"]["path"], "force_rate": fps,
                         "custom_width": 0, "custom_height": 0, "frame_load_cap": frames,
                         "skip_first_frames": spec["skip_frames"], "select_every_nth": 1}},
        "2": {"class_type": "DWPreprocessor",
              "inputs": {"image": ["1", 0], "detect_hand": "enable", "detect_body": "enable",
                         "detect_face": "disable", "resolution": 512,
                         "bbox_detector": "yolox_l.onnx",
                         "pose_estimator": "dw-ll_ucoco_384_bs5.torchscript.pt",
                         "scale_stick_for_xinsr_cn": "enable"}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0], "filename_prefix": f"{prefix}/pose"}},
        "4": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": f"{prefix}/src"}},
        "10": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CHECKPOINT}},
        "12": {"class_type": "ADE_StandardUniformContextOptions",
               "inputs": {"context_length": CONTEXT_LENGTH, "context_stride": 1,
                          "context_overlap": CONTEXT_OVERLAP, "fuse_method": "pyramid",
                          "use_on_equal_length": False, "start_percent": 0.0, "guarantee_steps": 1}},
        "11": {"class_type": "ADE_AnimateDiffLoaderGen1",
               "inputs": {"model": ["10", 0], "model_name": MOTION_MODULE,
                          "beta_schedule": BETA_SCHEDULE, "context_options": ["12", 0]}},
        "13": {"class_type": "IPAdapterUnifiedLoader",
               "inputs": {"model": ["11", 0], "preset": "PLUS FACE (portraits)"}},
        "14": {"class_type": "LoadImage", "inputs": {"image": inputs["face_image"]}},
        "15": {"class_type": "IPAdapterAdvanced",
               "inputs": {"model": ["13", 0], "ipadapter": ["13", 1], "image": ["14", 0],
                          "weight": IPA_WEIGHT, "weight_type": "linear", "combine_embeds": "concat",
                          "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only"}},
        "16": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["prompt"], "clip": ["10", 1]}},
        "17": {"class_type": "CLIPTextEncode", "inputs": {"text": spec["negative"], "clip": ["10", 1]}},
        "18": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": CONTROLNET}},
        "19": {"class_type": "SetUnionControlNetType", "inputs": {"control_net": ["18", 0], "type": "openpose"}},
        "20": {"class_type": "ACN_AdvancedControlNetApply_v2",
               "inputs": {"positive": ["16", 0], "negative": ["17", 0], "control_net": ["19", 0],
                          "image": ["2", 0], "strength": CN_STRENGTH, "start_percent": 0.0,
                          "end_percent": 1.0, "vae_optional": ["10", 2]}},
        "21": {"class_type": "EmptyLatentImage",
               "inputs": {"width": spec["width"], "height": spec["height"], "batch_size": frames}},
        "22": {"class_type": "KSampler",
               "inputs": {"model": ["15", 0], "seed": spec["seed"], "steps": STEPS, "cfg": CFG,
                          "sampler_name": SAMPLER, "scheduler": SCHEDULER, "positive": ["20", 0],
                          "negative": ["20", 1], "latent_image": ["21", 0], "denoise": 1.0}},
        "23": {"class_type": "VAEDecode", "inputs": {"samples": ["22", 0], "vae": ["10", 2]}},
        "24": {"class_type": "SaveImage", "inputs": {"images": ["23", 0], "filename_prefix": f"{prefix}/frame"}},
        "25": {"class_type": "VHS_VideoCombine",
               "inputs": {"images": ["23", 0], "frame_rate": fps, "loop_count": 0,
                          "filename_prefix": f"{prefix}/video", "format": "video/h264-mp4",
                          "pingpong": False, "save_output": True}},
    }
    if inputs.get("mask_image"):
        g["26"] = {"class_type": "LoadImageMask", "inputs": {"image": inputs["mask_image"], "channel": "red"}}
        g["15"]["inputs"]["attn_mask"] = ["26", 0]
    done = "24"
    if spec.get("face_detail"):
        people, rank = int(inputs.get("people") or 1), int(inputs.get("rank") or 0)
        pick = ({"target": "x1", "order": False, "take_start": rank, "take_count": 1} if people > 1
                else {"target": "area(=w*h)", "order": True, "take_start": 0, "take_count": 1})
        g["40"] = {"class_type": "UltralyticsDetectorProvider", "inputs": {"model_name": FACE_DETECTOR}}
        g["41"] = {"class_type": "ImpactSimpleDetectorSEGS_for_AD",
                   "inputs": {"bbox_detector": ["40", 0], "image_frames": ["23", 0], "bbox_threshold": 0.5,
                              "bbox_dilation": 0, "crop_factor": 3.0, "drop_size": 10,
                              "sub_threshold": 0.5, "sub_dilation": 0, "sub_bbox_expansion": 0,
                              "sam_mask_hint_threshold": 0.7, "masking_mode": "Pivot SEGS",
                              "segs_pivot": "Combined mask"}}
        g["42"] = {"class_type": "ImpactSEGSOrderedFilter", "inputs": dict(pick, segs=["41", 0])}
        if inputs.get("faceid") and inputs.get("face_found"):
            g["50"] = {"class_type": "IPAdapterUnifiedLoaderFaceID",
                       "inputs": {"model": ["11", 0], "preset": "FACEID PLUS V2",
                                  "lora_strength": FACEID_LORA, "provider": "CPU"}}
            g["43"] = {"class_type": "IPAdapterFaceID",
                       "inputs": {"model": ["50", 0], "ipadapter": ["50", 1], "image": ["14", 0],
                                  "weight": IPA_WEIGHT, "weight_faceidv2": FACEID_V2, "weight_type": "linear",
                                  "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                                  "embeds_scaling": "V only"}}
        else:
            g["43"] = {"class_type": "IPAdapterAdvanced",
                       "inputs": {"model": ["13", 0], "ipadapter": ["13", 1], "image": ["14", 0],
                                  "weight": IPA_WEIGHT, "weight_type": "linear", "combine_embeds": "concat",
                                  "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only"}}
        g["44"] = {"class_type": "CLIPTextEncode", "inputs": {"text": spec["face_prompt"], "clip": ["10", 1]}}
        g["45"] = {"class_type": "CLIPTextEncode", "inputs": {"text": FD_NEGATIVE, "clip": ["10", 1]}}
        g["46"] = {"class_type": "ToBasicPipe",
                   "inputs": {"model": ["43", 0], "clip": ["10", 1], "vae": ["10", 2],
                              "positive": ["44", 0], "negative": ["45", 0]}}
        g["47"] = {"class_type": "DetailerForEachPipeForAnimateDiff",
                   "inputs": {"image_frames": ["23", 0], "segs": ["42", 0], "guide_size": FD_GUIDE,
                              "guide_size_for": True, "max_size": FD_MAX, "seed": spec["seed"],
                              "steps": STEPS, "cfg": CFG, "sampler_name": SAMPLER, "scheduler": SCHEDULER,
                              "denoise": FD_DENOISE, "feather": 8, "basic_pipe": ["46", 0],
                              "refiner_ratio": 0.2, "noise_mask_feather": 20}}
        g["48"] = {"class_type": "SaveImage", "inputs": {"images": ["47", 0], "filename_prefix": f"{prefix}/fd_frame"}}
        g["49"] = {"class_type": "VHS_VideoCombine",
                   "inputs": {"images": ["47", 0], "frame_rate": fps, "loop_count": 0,
                              "filename_prefix": f"{prefix}/video_fd", "format": "video/h264-mp4",
                              "pingpong": False, "save_output": True}}
        done = "48"
    return g, done


_TEMPLATE_SPEC = {"reference_video": {"path": "<video>", "width": 1920, "height": 1080},
                  "prompt": "<prompt>", "negative": "<negative>", "face_prompt": "<face>", "seed": 1,
                  "target_fps": 8, "skip_frames": 0, "frames": 16, "width": 768, "height": 448,
                  "face_detail": True}
_TEMPLATE_INPUTS = {"face_image": "<face>", "mask_image": "<mask>", "face_found": True, "faceid": True,
                    "people": 2, "rank": 0}


def template_sha256() -> str:
    """Hash of the graph structure with fixed placeholders: changes only if the template does."""
    graph, _ = build_graph(_TEMPLATE_SPEC, _TEMPLATE_INPUTS, "<prefix>")
    return hashlib.sha256(json.dumps(graph, sort_keys=True).encode("utf-8")).hexdigest()


def validate_graph(graph: dict, info: dict) -> list[str]:
    """Every class exists, every input is declared, every combo value is offered."""
    problems: list[str] = []
    for node_id, node in graph.items():
        spec = info.get(node["class_type"])
        if not spec:
            problems.append(f"node {node_id}: class {node['class_type']} not in object_info")
            continue
        inputs = spec.get("input") or {}
        declared = set((inputs.get("required") or {})) | set((inputs.get("optional") or {}))
        for name, value in node["inputs"].items():
            if name not in declared:
                problems.append(f"node {node_id} ({node['class_type']}): unknown input {name!r}")
                continue
            if not isinstance(value, str):
                continue
            spec_in = (inputs.get("required") or {}).get(name) or (inputs.get("optional") or {}).get(name)
            choices = None
            if isinstance(spec_in, list) and spec_in:
                if isinstance(spec_in[0], list):
                    choices = spec_in[0]
                elif spec_in[0] == "COMBO" and len(spec_in) > 1 and isinstance(spec_in[1], dict):
                    choices = spec_in[1].get("options")
            if choices is not None and value not in choices:
                problems.append(f"node {node_id} ({node['class_type']}): {name}={value!r} not offered")
    return problems


# ---------------------------------------------------------------------------------------
# job runner (runs as its own process)
# ---------------------------------------------------------------------------------------

def _helper(*argv: str, timeout: int = 600) -> dict:
    import image_render
    out = subprocess.run([str(image_render.COMFY_PYTHON), str(FACES_HELPER), *argv],
                         capture_output=True, text=True, timeout=timeout,
                         env=dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8"))
    lines = [ln for ln in (out.stdout or "").splitlines() if ln.strip().startswith("{")]
    if out.returncode != 0 or not lines:
        raise RuntimeError(f"face helper failed (rc={out.returncode}): {(out.stderr or out.stdout)[-800:]}")
    return json.loads(lines[-1])


def _sample_frames(spec: dict, job_dir: Path) -> list[Path]:
    v = spec["reference_video"]
    start = spec["start_seconds"]
    span = spec["frames"] / spec["target_fps"]
    out = []
    for i in range(TRACK_SAMPLES):
        t = start + span * (i + 0.5) / TRACK_SAMPLES
        dest = job_dir / f"track_{i + 1:02d}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", v["path"],
                        "-frames:v", "1", str(dest)], check=True, timeout=120)
        if dest.is_file():
            out.append(dest)
    return out


def _probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "format=duration,size:stream=codec_name,width,height,r_frame_rate,nb_frames",
                          "-of", "json", str(path)], capture_output=True, text=True, timeout=60)
    return json.loads(out.stdout) if out.returncode == 0 else {"error": out.stderr.strip()}


class _GpuSampler:
    """nvidia-smi memory.used + temperature every 2 s while the prompt runs (passive)."""

    def __init__(self) -> None:
        import threading
        self.mem: list[int] = []
        self.temp: list[int] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        import thermal_guard
        while not self._stop.is_set():
            try:
                out = subprocess.run([str(thermal_guard.NVIDIA_SMI), "--query-gpu=memory.used,temperature.gpu",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10)
                mem, temp = (int(x.strip()) for x in out.stdout.strip().splitlines()[0].split(","))
                self.mem.append(mem)
                self.temp.append(temp)
            except Exception:
                pass
            self._stop.wait(2.0)

    def __enter__(self) -> "_GpuSampler":
        self._thread.start()
        return self

    def __exit__(self, *_exc) -> None:
        self._stop.set()
        self._thread.join(timeout=5)

    def summary(self) -> dict:
        return {"samples": len(self.mem), "interval_s": 2,
                "peak_mib": max(self.mem) if self.mem else None,
                "peak_temp_c": max(self.temp) if self.temp else None}


class _Job:
    def __init__(self, job_dir: Path):
        self.dir = job_dir
        self.spec = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        self.status: dict[str, Any] = {"job_id": self.spec["job_id"], "pid": os.getpid()}

    def set(self, state: str, **extra) -> None:
        self.status.update(extra, state=state, updated_at=_now())
        _write_json(self.dir / "status.json", self.status)
        print(f"[{time.strftime('%H:%M:%S')}] {state} {json.dumps(extra)[:300]}", flush=True)


def run_job(job_dir: Path) -> int:
    import image_render as ir
    import thermal_guard
    job = _Job(job_dir)
    spec, job_id = job.spec, job.spec["job_id"]
    prefix = f"{COMFY_SUBDIR}/{job_id}"
    manifest: dict[str, Any] = {"job_id": job_id, "template_version": TEMPLATE_VERSION,
                                "template_sha256": template_sha256(), "started_at": _now(),
                                "inputs": {"reference_video": spec["reference_video"],
                                           "character_image": spec["character_image"]},
                                "settings": {k: spec[k] for k in ("frames", "windows", "target_fps",
                                                                  "start_seconds", "width", "height",
                                                                  "size_measured", "seed", "target",
                                                                  "face_detail", "prompt", "negative",
                                                                  "face_prompt")},
                                "status": "failed", "outputs": [], "videos": []}
    proc = None
    owner_written = False
    try:
        # Claim the shared image-render owner before the ~1 minute of CPU analysis, so a still
        # render cannot take the backend in between (_write_owner refuses a live owner).
        job.set("claiming_gpu_owner")
        ir._write_owner()
        owner_written = True
        job.set("analysing_inputs")
        face_name, mask_name = f"mtr_{job_id}_face.png", None
        crop = _helper("crop", "--image", spec["character_image"]["path"], "--out", str(job_dir / "face_crop.png"))
        shutil.copy2(job_dir / "face_crop.png", ir.IMAGE_INPUT / face_name)
        samples = _sample_frames(spec, job_dir)
        faces = _helper("faces", "--frames", *[str(p) for p in samples])
        target = choose_target([f["faces"] for f in faces["frames"]], spec["target"])
        band_px = band_to_pixels(target.get("band"), spec)
        if band_px:
            from PIL import Image
            mask = Image.new("L", (spec["width"], spec["height"]), 0)
            mask.paste(255, (band_px[0], 0, band_px[1], spec["height"]))
            mask.save(job_dir / "ipadapter_mask.png")
            mask_name = f"mtr_{job_id}_mask.png"
            shutil.copy2(job_dir / "ipadapter_mask.png", ir.IMAGE_INPUT / mask_name)
        fid = faceid_installed()
        inputs = {"face_image": face_name, "mask_image": mask_name, "face_found": bool(crop.get("face_found")),
                  "faceid": fid["installed"], "people": target.get("people") or 1, "rank": target.get("rank") or 0}
        manifest["analysis"] = {"character_face": crop, "target": target, "mask_band_px": band_px,
                                "faceid": fid,
                                "identity_adapter_detail": (None if not spec["face_detail"] else
                                                            "FaceID Plus V2" if inputs["faceid"] and
                                                            inputs["face_found"] else "PLUS FACE")}
        graph, done_node = build_graph(spec, inputs, prefix)
        _write_json(job_dir / "graph.json", graph)
        manifest["graph_sha256"] = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()

        job.set("preflight")
        ir.preflight_execute()
        job.set("starting_backend")
        t0 = time.monotonic()
        proc = ir._start_owned_backend(face_detail=True, startup_timeout=900)
        manifest["backend_start_seconds"] = round(time.monotonic() - t0, 1)
        problems = validate_graph(graph, ir.object_info())
        if problems:
            raise RuntimeError("graph validation failed: " + " | ".join(problems))
        sampler = _GpuSampler()
        t1 = time.monotonic()
        try:
            with sampler:
                prompt_id = ir._post_prompt(graph)
                manifest["prompt_id"] = prompt_id
                job.set("rendering", prompt_id=prompt_id, frames=spec["frames"], windows=spec["windows"])
                ir._wait_for_outputs(prompt_id, proc, timeout_s=1800 + 60 * spec["frames"],
                                     output_node_ids={done_node})
        finally:
            manifest["render_seconds"] = round(time.monotonic() - t1, 1)
            manifest["gpu_during_render"] = sampler.summary()
        job.set("collecting")
        entry = ir._get_json(f"{ir.API}/history/{prompt_id}").get(prompt_id) or {}
        manifest["history_status"] = entry.get("status")
        for node_id, node in (entry.get("outputs") or {}).items():
            for key in ("images", "gifs"):
                for item in node.get(key, []):
                    path = ir.IMAGE_OUTPUT / (item.get("subfolder") or "") / item["filename"]
                    row = {"node": node_id, "path": str(path), "exists": path.is_file()}
                    if path.is_file():
                        row.update(size_bytes=path.stat().st_size, sha256=_sha(path))
                        if key == "gifs":
                            row["ffprobe"] = _probe(path)
                    manifest["videos" if key == "gifs" else "outputs"].append(row)
        counts = {n: sum(1 for o in manifest["outputs"] if o["node"] == n and o["exists"])
                  for n in ("3", "4", "24", "48")}
        manifest["frame_counts"] = {"planned": spec["frames"], "source": counts["4"], "pose": counts["3"],
                                    "generated": counts["24"],
                                    "face_detailed": counts["48"] if spec["face_detail"] else None}
        final_node = "49" if spec["face_detail"] else "25"
        final = next((v for v in manifest["videos"] if v["node"] == final_node and v["exists"]), None)
        expected = [counts["4"], counts["3"], counts["24"]] + ([counts["48"]] if spec["face_detail"] else [])
        verified = bool(final) and all(c == spec["frames"] for c in expected)
        if final:
            streams = (final.get("ffprobe") or {}).get("streams") or [{}]
            verified = verified and str(streams[0].get("nb_frames")) == str(spec["frames"])
        manifest["final_video"] = final
        manifest["verified_outputs"] = verified
        manifest["status"] = "complete" if verified else "incomplete_outputs"
    except Exception as exc:
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        job.set("failed", error=manifest["error"][:600])
    finally:
        try:
            ir._stop_owned_backend(proc)
        except Exception as exc:
            manifest["stop_error"] = str(exc)
        if owner_written:
            try:
                ir._release_owner()
            except Exception as exc:
                manifest["release_error"] = str(exc)
        try:
            manifest["gpu_after"] = thermal_guard.sample_gpu().__dict__
        except Exception as exc:
            manifest["gpu_after"] = str(exc)
    if manifest["status"] == "complete":
        try:
            job.set("identity_check")
            frames = sorted(p["path"] for p in manifest["outputs"]
                            if p["node"] == ("48" if spec["face_detail"] else "24") and p["exists"])
            target = manifest["analysis"]["target"]
            manifest["identity_check"] = _helper("score", "--ref", spec["character_image"]["path"],
                                                 "--rank", str(target.get("rank") or 0),
                                                 "--people", str(target.get("people") or 1),
                                                 "--frames", *frames, timeout=1800)
        except Exception as exc:
            manifest["identity_check"] = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    manifest["finished_at"] = _now()
    manifest["acceptance"] = ("not accepted: likeness and motion need the operator's frame-level visual "
                              "check; the identity score is a machine signal only")
    _write_json(job_dir / "manifest.json", manifest)
    job.set(manifest["status"] if manifest["status"] != "failed" else "failed",
            final_video=(manifest.get("final_video") or {}).get("path"))
    return 0 if manifest["status"] == "complete" else 1


# ---------------------------------------------------------------------------------------
# status (read-only; used by the status tool)
# ---------------------------------------------------------------------------------------

def _pid_alive(pid) -> bool:
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in (out.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def job_status(job_id: str) -> dict:
    safe = Path(str(job_id or "")).name
    if not safe.startswith("mtr_"):
        raise RenderRequestError("job_id must be an mtr_... id returned by render_video_from_reference")
    job_dir = JOBS_ROOT / safe
    if not job_dir.is_dir():
        raise RenderRequestError(f"no such job: {safe}")
    status = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
    out: dict[str, Any] = {"job_id": safe, "job_dir": str(job_dir), "state": status.get("state"),
                           "updated_at": status.get("updated_at")}
    manifest_path = job_dir / "manifest.json"
    if manifest_path.is_file():
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
        out.update(state=m.get("status"), verified_outputs=m.get("verified_outputs"),
                   final_video=m.get("final_video"), frame_counts=m.get("frame_counts"),
                   identity_check={k: (m.get("identity_check") or {}).get(k)
                                   for k in ("available", "mean", "min", "detected", "frames", "caveat")},
                   analysis_summary={"target": (m.get("analysis") or {}).get("target"),
                                     "identity_adapter_detail": (m.get("analysis") or {}).get(
                                         "identity_adapter_detail")},
                   render_seconds=m.get("render_seconds"), gpu_during_render=m.get("gpu_during_render"),
                   error=m.get("error"),
                   manifest=str(manifest_path), acceptance=m.get("acceptance"))
    elif status.get("pid") and not _pid_alive(status.get("pid")):
        out["state"] = "finished_or_crashed"
        out["note"] = "the job process is gone and wrote no manifest; see runner.log"
    else:
        out["note"] = ("still running: backend start can take up to ~15 minutes on a cold disk, "
                       "then about 5-15 minutes per 24 frames; poll again later")
    log = job_dir / "runner.log"
    if log.is_file():
        out["log_tail"] = log.read_text(encoding="utf-8", errors="replace")[-1500:]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--job-dir", required=True)
    args = ap.parse_args(argv)
    job_dir = Path(args.job_dir).resolve()
    if not _under(job_dir, JOBS_ROOT.resolve()):
        raise SystemExit(f"job dir must be under {JOBS_ROOT}")
    return run_job(job_dir)


if __name__ == "__main__":
    raise SystemExit(main())
