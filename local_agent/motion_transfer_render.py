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

Segment chaining (2026-09-26l). One AnimateDiff job holds every frame in system RAM
(+14.4 GB at 180 frames, CHANGELOG 2026-09-26k), so a long clip is rendered as a chain of
independent segments instead: each segment is its own prompt on the same backend, walks the
next slice of the reference clip, and starts from the previous segment's last HELD_FRAMES
output frames, which are VAE-encoded, batched ahead of the new empty latents and pinned by a
per-frame latent noise mask (core KSamplerX0Inpaint blends masked-out frames back to the init
at every step; AnimateDiff-Evolved's context windows never touch the mask). The held frames
are dropped when the segments are stitched, so every delivered frame is rendered once. RAM
per segment is fixed by the segment length, not the total.
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
# after a longer run has been measured (time, peak VRAM, RAM, frame count, visual check).
# 2026-09-26k: 180 frames (15 windows) measured: render 1279 s, peak VRAM 15 881 MiB (flat
# vs. 63 frames), peak 74 C, system RAM +14.4 GB over baseline (29.8 of 30.9 GB used).
MAX_FRAMES = 180
# RAM, not VRAM, bounds the length (frames are held in system memory). Free RAM needed at
# job start: the measured +14.4 GB at 180 frames scaled by length, plus 1.5 GB margin.
RAM_MEASURED_GB_AT_180 = 14.4
RAM_MARGIN_GB = 1.5
# Segment chaining (2026-09-26l, opt-in: chain=true or segment_seconds). The request is split
# into segments of at most SEGMENT_FRAMES_DEFAULT new frames; every
# segment after the first also re-renders the previous segment's last HELD_FRAMES output
# frames, pinned by a latent noise mask, so the new frames continue from real pixels.
SEGMENT_FRAMES_DEFAULT = 64
HELD_FRAMES = 4
# Total delivered frames of a chained job. Time is linear (about 7-9 s per rendered frame plus
# HELD_FRAMES per seam); RAM is per segment. 600 = 75 s at 8 fps.
MAX_CHAIN_FRAMES = 600
INIT_MODES = ("held", "img2img")
INIT_MODE_DEFAULT = "held"
IMG2IMG_DENOISE_DEFAULT = 0.7


def ram_needed_gb(frames: int) -> float:
    return round(RAM_MEASURED_GB_AT_180 * frames / 180 + RAM_MARGIN_GB, 1)


def ram_check(frames: int) -> dict:
    """Free system RAM vs the measured need; ``ok`` False means do not start the job."""
    try:
        import psutil
        free = psutil.virtual_memory().available / 2**30
    except Exception as exc:  # no psutil: report, do not block on an unmeasurable value
        return {"ok": True, "available_gb": None, "needed_gb": ram_needed_gb(frames),
                "note": f"RAM not measurable ({type(exc).__name__})"}
    need = ram_needed_gb(frames)
    return {"ok": free >= need, "available_gb": round(free, 1), "needed_gb": need}


def _windows(frames: int) -> int:
    if frames <= CONTEXT_LENGTH:
        return 1
    return 1 + math.ceil((frames - CONTEXT_LENGTH) / (CONTEXT_LENGTH - CONTEXT_OVERLAP))


def plan_segments(total: int, seg_new: int, held: int = HELD_FRAMES) -> list[dict]:
    """Split ``total`` delivered frames into balanced segments of <= ``seg_new`` new frames.

    Segment i > 0 re-renders the previous segment's last ``held`` frames first (they are
    dropped at stitch time), so its source slice starts ``held`` frames before the frames it
    delivers. ``source_offset`` is relative to the job's own start (skip_frames).
    """
    if total <= 0 or seg_new <= 0 or held < 0:
        raise ValueError("plan_segments needs total > 0, seg_new > 0, held >= 0")
    n = max(1, math.ceil(total / seg_new))
    q, r = divmod(total, n)
    parts = [q + 1] * r + [q] * (n - r)
    out, delivered = [], 0
    for i, new in enumerate(parts):
        h = 0 if i == 0 else min(held, delivered)
        frames = h + new
        out.append({"index": i, "source_offset": delivered - h, "held": h, "new": new,
                    "frames": frames, "windows": _windows(frames)})
        delivered += new
    return out


def ram_frames(spec: dict) -> int:
    """Frames that bound RAM: the longest segment of a chained job, else the whole job."""
    if spec.get("chained") and spec.get("segments"):
        return max(s["frames"] for s in spec["segments"])
    return int(spec["frames"])


def rendered_frames(spec: dict) -> int:
    """Frames the GPU renders (held frames included), for time estimates."""
    if spec.get("chained") and spec.get("segments"):
        return sum(s["frames"] for s in spec["segments"])
    return int(spec["frames"])


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
    chain_arg = args.get("chain")
    if chain_arg not in (None, "", "auto", True, False):
        raise RenderRequestError("chain must be true, false or omitted (auto)")
    seg_s = args.get("segment_seconds")
    try:
        seg_s = float(seg_s) if seg_s not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise RenderRequestError(f"segment_seconds invalid: {exc}") from exc
    if seg_s is not None and seg_s <= 0:
        raise RenderRequestError("segment_seconds must be > 0")
    # Chaining is opt-in (chain=true or segment_seconds) until a seam scheme measures as
    # continuous: the held-frame seam of 2026-09-26l is a visible cut (see the changelog).
    chained = chain_arg is True or seg_s is not None
    if not chained and frames > MAX_FRAMES:
        seconds = MAX_FRAMES / fps
        raise RenderRequestError(
            f"{frames} frames requested; one job is validated up to {MAX_FRAMES} frames "
            f"({seconds:.1f} s at {fps:g} fps). Pass max_seconds <= {seconds:.1f} (and start_seconds "
            "to choose the section), or pass chain=true to render chained segments (experimental, "
            "2026-09-26l: each seam between segments is currently a visible cut)")
    if chained and frames > MAX_CHAIN_FRAMES:
        raise RenderRequestError(
            f"{frames} frames requested; chained renders are limited to {MAX_CHAIN_FRAMES} frames "
            f"({MAX_CHAIN_FRAMES / fps:.1f} s at {fps:g} fps) per job. Pass max_seconds/start_seconds "
            "to choose a section")
    width, height = output_size(vinfo["width"], vinfo["height"])
    spec = {
        "template_version": TEMPLATE_VERSION,
        "reference_video": vinfo, "character_image": sinfo,
        "prompt": prompt, "negative": negative, "face_prompt": face_prompt, "seed": seed,
        "target_fps": fps, "start_seconds": start_s, "skip_frames": int(round(start_s * fps)),
        "frames": frames, "windows": _windows(frames), "width": width, "height": height,
        "size_measured": (width, height) in MEASURED_SIZES,
        "target": target, "face_detail": face_detail,
        "likeness_attestation": True,
        "chained": False, "segments": None, "segment_frames": None, "held_frames": 0, "init_mode": None,
    }
    if chained:
        seg_new = int(round(seg_s * fps)) if seg_s is not None else SEGMENT_FRAMES_DEFAULT
        if not MIN_FRAMES <= seg_new <= MAX_FRAMES - HELD_FRAMES:
            raise RenderRequestError(
                f"segment_seconds gives {seg_new} frames per segment; allowed {MIN_FRAMES}-"
                f"{MAX_FRAMES - HELD_FRAMES} ({MIN_FRAMES / fps:.1f}-{(MAX_FRAMES - HELD_FRAMES) / fps:.1f} s "
                f"at {fps:g} fps)")
        segments = plan_segments(frames, seg_new, HELD_FRAMES)
        if len(segments) > 1:
            spec.update(chained=True, segments=segments, segment_frames=seg_new, held_frames=HELD_FRAMES,
                        init_mode=INIT_MODE_DEFAULT, windows=sum(s["windows"] for s in segments))
    return spec


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


def choose_target(frames: list[list[list[float]]], target: str, prev_centre: float | None = None) -> dict:
    """Pick and follow one face across sampled frames; derive its horizontal band.

    ``frames``: per sampled frame, faces as normalised [x1, y1, x2, y2, score].
    Returns people (max faces in a frame), rank (target's left-to-right index where
    all people are visible), and band [lo, hi] in source-normalised x: the part of the
    frame closer to the target than to its neighbours (median over frames), or None
    for a one-person clip. ``prev_centre`` (a chained segment after the first) continues
    the person tracked so far: the face nearest that centre in the first sampled frame.
    """
    seen = [f for f in frames if f]
    if not seen:
        return {"people": 0, "rank": 0, "band": None, "reason": "no face in any sampled frame"}
    people = max(len(f) for f in seen)
    centre = lambda b: (b[0] + b[2]) / 2.0  # noqa: E731
    area = lambda b: (b[2] - b[0]) * (b[3] - b[1])  # noqa: E731
    first = max(seen, key=len)
    if prev_centre is not None:
        first = seen[0]
        pick = min(first, key=lambda b: abs(centre(b) - prev_centre))
    elif target == "left":
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

def _segment_span(spec: dict, segment: dict | None) -> tuple[int, int, int]:
    """(frames to load/render, held frames, source frames to skip) for a job or one segment."""
    if segment is None:
        return int(spec["frames"]), 0, int(spec["skip_frames"])
    return int(segment["frames"]), int(segment["held"]), int(spec["skip_frames"]) + int(segment["source_offset"])


def build_graph(spec: dict, inputs: dict, prefix: str, segment: dict | None = None) -> tuple[dict, str]:
    """Return (ComfyUI API graph, id of the node whose images mark completion).

    ``inputs``: face_image (file in the owned input dir), mask_image (file or None),
    face_found (bool), faceid (bool), people (int), rank (int); for a chained segment with
    held frames also init_dir (the previous segment's last frames, one PNG each) and
    noise_mask_dir (one mask PNG per frame: black = keep the held frame, white = generate).
    ``segment`` (from plan_segments) narrows the loader to that slice; None is the single-job
    graph, unchanged from 2026-09-26j.
    """
    frames, held, skip = _segment_span(spec, segment)
    fps = spec["target_fps"]
    g: dict[str, dict] = {
        "1": {"class_type": "VHS_LoadVideoPath",
              "inputs": {"video": spec["reference_video"]["path"], "force_rate": fps,
                         "custom_width": 0, "custom_height": 0, "frame_load_cap": frames,
                         "skip_first_frames": skip, "select_every_nth": 1}},
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
    if held and inputs.get("init_dir"):
        mode = spec.get("init_mode") or INIT_MODE_DEFAULT
        if mode not in INIT_MODES:
            raise ValueError(f"init_mode must be one of {INIT_MODES}")
        if mode == "held":
            # The previous segment's last `held` frames, encoded and batched ahead of the new
            # empty latents; the noise mask pins them so sampling only generates the rest.
            g["30"] = {"class_type": "VHS_LoadImagesPath",
                       "inputs": {"directory": inputs["init_dir"], "image_load_cap": held,
                                  "skip_first_images": 0, "select_every_nth": 1}}
            g["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["30", 0], "vae": ["10", 2]}}
            g["21"]["inputs"]["batch_size"] = frames - held
            g["32"] = {"class_type": "LatentBatch", "inputs": {"samples1": ["31", 0], "samples2": ["21", 0]}}
            g["33"] = {"class_type": "VHS_LoadImagesPath",
                       "inputs": {"directory": inputs["noise_mask_dir"], "image_load_cap": frames,
                                  "skip_first_images": 0, "select_every_nth": 1}}
            g["34"] = {"class_type": "ImageToMask", "inputs": {"image": ["33", 0], "channel": "red"}}
            g["35"] = {"class_type": "SetLatentNoiseMask", "inputs": {"samples": ["32", 0], "mask": ["34", 0]}}
            g["22"]["inputs"]["latent_image"] = ["35", 0]
        else:
            # img2img: every frame starts from the previous segment's last frame at a partial
            # denoise (investigation alternative, 2026-09-26l; not the shipped default).
            g["30"] = {"class_type": "VHS_LoadImagesPath",
                       "inputs": {"directory": inputs["init_dir"], "image_load_cap": 1,
                                  "skip_first_images": held - 1, "select_every_nth": 1}}
            g["36"] = {"class_type": "RepeatImageBatch", "inputs": {"image": ["30", 0], "amount": frames}}
            g["31"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["36", 0], "vae": ["10", 2]}}
            g["22"]["inputs"]["latent_image"] = ["31", 0]
            g["22"]["inputs"]["denoise"] = float(spec.get("init_denoise") or IMG2IMG_DENOISE_DEFAULT)
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
_TEMPLATE_SEGMENT = {"index": 1, "source_offset": 20, "held": 4, "new": 24, "frames": 28, "windows": 2}
_TEMPLATE_INPUTS_CHAIN = dict(_TEMPLATE_INPUTS, init_dir="<init>", noise_mask_dir="<masks>")


def template_sha256(chained: bool = False) -> str:
    """Hash of the graph structure with fixed placeholders: changes only if the template does.

    ``chained``: the graph of a segment after the first (held frames + noise mask, init_mode held).
    """
    if chained:
        spec = dict(_TEMPLATE_SPEC, init_mode="held")
        graph, _ = build_graph(spec, _TEMPLATE_INPUTS_CHAIN, "<prefix>", _TEMPLATE_SEGMENT)
    else:
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


def _sample_frames(spec: dict, job_dir: Path, segment: dict | None = None) -> list[Path]:
    v = spec["reference_video"]
    frames, _held, skip = _segment_span(spec, segment)
    start = skip / spec["target_fps"]
    span = frames / spec["target_fps"]
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
    """nvidia-smi memory.used + temperature (and psutil system RAM) every 2 s while the prompt runs."""

    def __init__(self) -> None:
        import threading
        self.mem: list[int] = []
        self.temp: list[int] = []
        self.ram: list[float] = []
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
            try:
                import psutil
                self.ram.append(psutil.virtual_memory().used / 2**30)
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
                "peak_temp_c": max(self.temp) if self.temp else None,
                "ram_used_gb_first": round(self.ram[0], 2) if self.ram else None,
                "ram_used_gb_peak": round(max(self.ram), 2) if self.ram else None,
                "ram_samples": len(self.ram)}


class _Job:
    def __init__(self, job_dir: Path):
        self.dir = job_dir
        self.spec = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        self.status: dict[str, Any] = {"job_id": self.spec["job_id"], "pid": os.getpid()}

    def set(self, state: str, **extra) -> None:
        self.status.update(extra, state=state, updated_at=_now())
        _write_json(self.dir / "status.json", self.status)
        print(f"[{time.strftime('%H:%M:%S')}] {state} {json.dumps(extra)[:300]}", flush=True)


def write_segment_inputs(job_dir: Path, segment: dict, tail_frames: list[str],
                         size: tuple[int, int]) -> dict:
    """Held init frames (byte copies of the previous segment's last outputs) + the noise-mask batch.

    Written under <job_dir>/segNN/{init,noise_mask}/ so VHS_LoadImagesPath loads exactly them,
    in name order. Mask value 0 (black) keeps a held frame, 255 (white) generates a new one.
    """
    from PIL import Image
    held = int(segment["held"])
    if len(tail_frames) < held:
        raise RuntimeError(f"segment {segment['index'] + 1} needs {held} held frames; only "
                           f"{len(tail_frames)} available from the previous segment")
    seg_dir = job_dir / f"seg{segment['index'] + 1:02d}"
    init_dir, mask_dir = seg_dir / "init", seg_dir / "noise_mask"
    init_dir.mkdir(parents=True, exist_ok=True)
    mask_dir.mkdir(parents=True, exist_ok=True)
    inits = []
    for i, src in enumerate(tail_frames[-held:], 1):
        dest = init_dir / f"init_{i:05d}.png"
        shutil.copy2(src, dest)
        inits.append({"from": str(src), "path": str(dest), "sha256": _sha(dest)})
    w, h = size
    black, white = Image.new("L", (w, h), 0), Image.new("L", (w, h), 255)
    for i in range(1, int(segment["frames"]) + 1):
        (black if i <= held else white).save(mask_dir / f"mask_{i:05d}.png")
    return {"init_dir": str(init_dir), "noise_mask_dir": str(mask_dir), "init_frames": inits,
            "mask_frames": int(segment["frames"]), "held_masked": held}


def stitch_frames(frames: list[str], out_dir: Path, fps: float, name: str = "final_chained.mp4") -> dict:
    """Hard-link (or copy) the delivered frames in order and encode one h264 mp4 with ffmpeg."""
    seq = out_dir / "stitched_frames"
    seq.mkdir(parents=True, exist_ok=True)
    for i, src in enumerate(frames, 1):
        dest = seq / f"f_{i:05d}.png"
        try:
            os.link(src, dest)
        except OSError:
            shutil.copy2(src, dest)
    out = out_dir / name
    cmd = ["ffmpeg", "-v", "error", "-y", "-framerate", f"{fps:g}", "-i", str(seq / "f_%05d.png"),
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "17", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True, timeout=900)
    row = {"node": "stitched", "path": str(out), "exists": out.is_file(), "frames_dir": str(seq),
           "frames_linked": len(frames), "ffmpeg": cmd}
    if out.is_file():
        row.update(size_bytes=out.stat().st_size, sha256=_sha(out), ffprobe=_probe(out))
    return row


def sequence_metrics(frames: list[str], seams: list[int], roundtrips: list[tuple[str, str]] = ()) -> dict:
    """Frame-to-frame mean |diff| (0-255) along the delivered sequence, seams called out.

    ``seams``: delivered indices (0-based) of the first frame of every segment after the first;
    the seam change is f2f[s - 1]. ``roundtrips``: (init png, rendered held png) pairs, whose
    difference is the VAE round trip (+ detail pass) of a held frame. Also the per-frame mean
    RGB, so lighting/colour drift can be read along the clip. CPU only.
    """
    import numpy as np
    from PIL import Image

    def load(p):
        return np.asarray(Image.open(p).convert("RGB"), dtype=np.float32)

    prev, f2f, mean_rgb = None, [], []
    for p in frames:
        a = load(p)
        mean_rgb.append([round(float(x), 2) for x in a.reshape(-1, 3).mean(axis=0)])
        if prev is not None:
            f2f.append(round(float(np.abs(a - prev).mean()), 3))
        prev = a
    seam_set = {s for s in seams if 0 < s < len(frames)}
    others = [v for i, v in enumerate(f2f) if (i + 1) not in seam_set]
    med = round(float(statistics.median(others)), 3) if others else None
    p90 = round(float(np.percentile(others, 90)), 3) if others else None
    seam_rows = []
    for s in sorted(seam_set):
        v = f2f[s - 1]
        seam_rows.append({"index": s, "f2f": v, "ratio_to_median": round(v / med, 2) if med else None,
                          "mean_rgb_before": mean_rgb[s - 1], "mean_rgb_after": mean_rgb[s]})
    rt = []
    for init, out in roundtrips:
        rt.append({"init": init, "rendered": out,
                   "mean_abs_diff": round(float(np.abs(load(init) - load(out)).mean()), 3)})
    return {"frames": len(frames), "f2f_median": med, "f2f_p90": p90,
            "f2f_max": round(max(others), 3) if others else None, "seams": seam_rows,
            "roundtrip": rt, "mean_rgb": mean_rgb, "f2f": f2f}


def _collect(ir, prompt_id: str) -> tuple[Any, list[dict], list[dict]]:
    entry = ir._get_json(f"{ir.API}/history/{prompt_id}").get(prompt_id) or {}
    outputs, videos = [], []
    for node_id, node in (entry.get("outputs") or {}).items():
        for key in ("images", "gifs"):
            for item in node.get(key, []):
                path = ir.IMAGE_OUTPUT / (item.get("subfolder") or "") / item["filename"]
                row = {"node": node_id, "path": str(path), "exists": path.is_file()}
                if path.is_file():
                    row.update(size_bytes=path.stat().st_size, sha256=_sha(path))
                    if key == "gifs":
                        row["ffprobe"] = _probe(path)
                (videos if key == "gifs" else outputs).append(row)
    return entry.get("status"), outputs, videos


def _frames_of(outputs: list[dict], node: str) -> list[str]:
    return sorted(o["path"] for o in outputs if o["node"] == node and o["exists"])


def run_job(job_dir: Path) -> int:
    import image_render as ir
    import thermal_guard
    job = _Job(job_dir)
    spec, job_id = job.spec, job.spec["job_id"]
    prefix = f"{COMFY_SUBDIR}/{job_id}"
    chained = bool(spec.get("chained"))
    segments: list = list(spec["segments"]) if chained else [None]
    final_node, final_frames_node = ("49", "48") if spec["face_detail"] else ("25", "24")
    manifest: dict[str, Any] = {"job_id": job_id, "template_version": TEMPLATE_VERSION,
                                "template_sha256": template_sha256(), "started_at": _now(),
                                "inputs": {"reference_video": spec["reference_video"],
                                           "character_image": spec["character_image"]},
                                "settings": {k: spec.get(k) for k in ("frames", "windows", "target_fps",
                                                                      "start_seconds", "width", "height",
                                                                      "size_measured", "seed", "target",
                                                                      "face_detail", "prompt", "negative",
                                                                      "face_prompt", "chained",
                                                                      "segment_frames", "held_frames",
                                                                      "init_mode", "init_denoise",
                                                                      "segments")},
                                "chained": chained, "status": "failed", "outputs": [], "videos": []}
    if chained:
        manifest["template_sha256_chained"] = template_sha256(chained=True)
        manifest["segments"] = []
    proc = None
    owner_written = False
    kept: list[str] = []
    seam_index: list[int] = []
    roundtrips: list[tuple[str, str]] = []
    try:
        # Claim the shared image-render owner before the ~1 minute of CPU analysis, so a still
        # render cannot take the backend in between (_write_owner refuses a live owner).
        job.set("claiming_gpu_owner")
        ir._write_owner()
        owner_written = True
        job.set("analysing_inputs")
        face_name = f"mtr_{job_id}_face.png"
        crop = _helper("crop", "--image", spec["character_image"]["path"], "--out", str(job_dir / "face_crop.png"))
        shutil.copy2(job_dir / "face_crop.png", ir.IMAGE_INPUT / face_name)
        fid = faceid_installed()
        manifest["analysis"] = {"character_face": crop, "faceid": fid,
                                "identity_adapter_detail": (None if not spec["face_detail"] else
                                                            "FaceID Plus V2" if fid["installed"] and
                                                            crop.get("face_found") else "PLUS FACE")}
        job.set("preflight")
        manifest["ram_at_start"] = ram_check(ram_frames(spec))
        if not manifest["ram_at_start"]["ok"]:
            raise RuntimeError(f"not enough free system RAM for {ram_frames(spec)} frames"
                               f"{' per segment' if chained else ''}: "
                               f"{manifest['ram_at_start']['available_gb']} GB free, "
                               f"{manifest['ram_at_start']['needed_gb']} GB needed; close other programs "
                               "or render a shorter section")
        ir.preflight_execute()
        job.set("starting_backend")
        t0 = time.monotonic()
        proc = ir._start_owned_backend(face_detail=True, startup_timeout=900)
        manifest["backend_start_seconds"] = round(time.monotonic() - t0, 1)
        info = ir.object_info()
        prev_centre = None
        tail: list[str] = []
        for seg in segments:
            idx = 0 if seg is None else int(seg["index"])
            seg_prefix = prefix if seg is None else f"{prefix}/seg{idx + 1:02d}"
            seg_dir = job_dir if seg is None else job_dir / f"seg{idx + 1:02d}"
            seg_dir.mkdir(parents=True, exist_ok=True)
            frames_n, held, _skip = _segment_span(spec, seg)
            rec: dict[str, Any] = {"index": idx, "prefix": seg_prefix, "frames": frames_n, "held": held,
                                   "new": frames_n - held,
                                   "source_offset": 0 if seg is None else seg["source_offset"],
                                   "windows": _windows(frames_n)}
            samples = _sample_frames(spec, seg_dir, seg)
            faces = _helper("faces", "--frames", *[str(p) for p in samples])
            target = choose_target([f["faces"] for f in faces["frames"]], spec["target"], prev_centre)
            if target.get("track"):
                prev_centre = target["track"][-1]
            band_px = band_to_pixels(target.get("band"), spec)
            mask_name = None
            if band_px:
                from PIL import Image
                mask = Image.new("L", (spec["width"], spec["height"]), 0)
                mask.paste(255, (band_px[0], 0, band_px[1], spec["height"]))
                mask.save(seg_dir / "ipadapter_mask.png")
                mask_name = f"mtr_{job_id}_mask.png" if seg is None else f"mtr_{job_id}_s{idx + 1:02d}_mask.png"
                shutil.copy2(seg_dir / "ipadapter_mask.png", ir.IMAGE_INPUT / mask_name)
            inputs = {"face_image": face_name, "mask_image": mask_name, "face_found": bool(crop.get("face_found")),
                      "faceid": fid["installed"], "people": target.get("people") or 1,
                      "rank": target.get("rank") or 0}
            rec["analysis"] = {"target": target, "mask_band_px": band_px}
            if held:
                seed_inputs = write_segment_inputs(job_dir, seg, tail, (spec["width"], spec["height"]))
                inputs.update(init_dir=seed_inputs["init_dir"], noise_mask_dir=seed_inputs["noise_mask_dir"])
                rec["seed_inputs"] = seed_inputs
            graph, done_node = build_graph(spec, inputs, seg_prefix, seg)
            _write_json(seg_dir / "graph.json", graph)
            rec["graph_sha256"] = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
            problems = validate_graph(graph, info)
            if problems:
                raise RuntimeError("graph validation failed: " + " | ".join(problems))
            if idx > 0:
                # Between segments: the same start rule as before a job (<= 70 C, else wait for 60 C).
                thermal_guard.wait_before_render(lambda message: print(message, flush=True))
            rec["ram_before"] = ram_check(frames_n)
            sampler = _GpuSampler()
            t1 = time.monotonic()
            try:
                with sampler:
                    prompt_id = ir._post_prompt(graph)
                    rec["prompt_id"] = prompt_id
                    job.set("rendering", prompt_id=prompt_id, segment=idx + 1, segments=len(segments),
                            frames=frames_n, windows=rec["windows"])
                    ir._wait_for_outputs(prompt_id, proc, timeout_s=1800 + 60 * frames_n,
                                         output_node_ids={done_node})
            finally:
                rec["render_seconds"] = round(time.monotonic() - t1, 1)
                rec["gpu_during_render"] = sampler.summary()
            job.set("collecting", segment=idx + 1, segments=len(segments))
            rec["history_status"], rec["outputs"], rec["videos"] = _collect(ir, prompt_id)
            counts = {n: sum(1 for o in rec["outputs"] if o["node"] == n and o["exists"])
                      for n in ("3", "4", "24", "48")}
            rec["frame_counts"] = {"planned": frames_n, "source": counts["4"], "pose": counts["3"],
                                   "generated": counts["24"],
                                   "face_detailed": counts["48"] if spec["face_detail"] else None}
            expected = [counts["4"], counts["3"], counts["24"]] + ([counts["48"]] if spec["face_detail"] else [])
            rec["verified"] = all(c == frames_n for c in expected)
            rec["final_video"] = next((v for v in rec["videos"] if v["node"] == final_node and v["exists"]), None)
            final_frames = _frames_of(rec["outputs"], final_frames_node)
            if held and len(final_frames) >= held:
                seam_index.append(len(kept))
                for init, out in zip(rec["seed_inputs"]["init_frames"], final_frames[:held]):
                    roundtrips.append((init["path"], out))
            kept.extend(final_frames[held:])
            tail = final_frames
            manifest["outputs"].extend(rec["outputs"])
            manifest["videos"].extend(rec["videos"])
            if chained:
                manifest["segments"].append(rec)
                _write_json(job_dir / "manifest.json", manifest)  # evidence so far, after every segment
                job.set("segment_complete", segment=idx + 1, segments=len(segments), verified=rec["verified"],
                        ram_used_gb_peak=rec["gpu_during_render"].get("ram_used_gb_peak"))
            else:
                for k in ("prompt_id", "history_status", "render_seconds", "gpu_during_render",
                          "frame_counts", "final_video", "graph_sha256"):
                    manifest[k] = rec.get(k)
                manifest["analysis"].update(rec["analysis"])
        if chained:
            job.set("stitching", delivered=len(kept), planned=spec["frames"])
            stitched = stitch_frames(kept, job_dir, spec["target_fps"])
            manifest["videos"].append(stitched)
            manifest["final_video"] = stitched
            segs = manifest["segments"]
            manifest["frame_counts"] = {
                "planned": spec["frames"], "delivered": len(kept),
                "rendered": sum(r["frames"] for r in segs),
                "source": sum(r["frame_counts"]["source"] for r in segs),
                "pose": sum(r["frame_counts"]["pose"] for r in segs),
                "generated": sum(r["frame_counts"]["generated"] for r in segs),
                "face_detailed": (sum(r["frame_counts"]["face_detailed"] or 0 for r in segs)
                                  if spec["face_detail"] else None)}
            streams = (stitched.get("ffprobe") or {}).get("streams") or [{}]
            verified = (len(segs) == len(segments) and all(r["verified"] for r in segs)
                        and len(kept) == spec["frames"] and stitched.get("exists")
                        and str(streams[0].get("nb_frames")) == str(spec["frames"]))
        else:
            final = manifest.get("final_video")
            verified = bool(final) and bool(manifest.get("frame_counts")) and all(
                manifest["frame_counts"][k] == spec["frames"]
                for k in (("source", "pose", "generated", "face_detailed") if spec["face_detail"]
                          else ("source", "pose", "generated")))
            if final:
                streams = (final.get("ffprobe") or {}).get("streams") or [{}]
                verified = verified and str(streams[0].get("nb_frames")) == str(spec["frames"])
        manifest["verified_outputs"] = bool(verified)
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
    if chained and kept:
        try:
            job.set("sequence_metrics")
            manifest["sequence"] = sequence_metrics(kept, seam_index, roundtrips)
        except Exception as exc:
            manifest["sequence"] = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    if manifest["status"] == "complete":
        try:
            job.set("identity_check")
            target = (manifest["analysis"].get("target") if not chained
                      else manifest["segments"][0]["analysis"]["target"])
            frames_file = job_dir / "identity_frames.txt"
            frames_file.write_text("\n".join(kept) + "\n", encoding="utf-8")
            manifest["identity_check"] = _helper("score", "--ref", spec["character_image"]["path"],
                                                 "--rank", str(target.get("rank") or 0),
                                                 "--people", str(target.get("people") or 1),
                                                 "--frames-file", str(frames_file), timeout=3600)
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
        if m.get("chained"):
            segs = m.get("segments") or []
            seq = m.get("sequence") or {}
            planned = (m.get("settings") or {}).get("segments") or []
            out.update(chained=True, segments_done=len(segs), segments_total=len(planned) or None,
                       segments=[dict({k: r.get(k) for k in ("index", "frames", "held", "new", "verified",
                                                              "render_seconds", "prompt_id")},
                                      ram_used_gb_peak=(r.get("gpu_during_render") or {}).get("ram_used_gb_peak"),
                                      peak_mib=(r.get("gpu_during_render") or {}).get("peak_mib"))
                                 for r in segs],
                       seams=seq.get("seams"), f2f_median=seq.get("f2f_median"),
                       render_seconds=sum(r.get("render_seconds") or 0 for r in segs))
            if not m.get("finished_at"):
                out["state"] = status.get("state")
                out["note"] = (f"chained job in progress: {len(segs)} of {len(planned) or '?'} segment(s) "
                               "rendered so far; the manifest is rewritten after every segment")
    elif status.get("pid") and not _pid_alive(status.get("pid")):
        out["state"] = "finished_or_crashed"
        out["note"] = "the job process is gone and wrote no manifest; see runner.log"
    else:
        out["note"] = ("still running: backend start can take up to ~15 minutes on a cold disk, "
                       "then about 7-9 seconds per frame (180 frames took 21 minutes); poll again later")
    if status.get("segments"):
        out["segment"] = status.get("segment")
        out["segments_total"] = status.get("segments")
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
