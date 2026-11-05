#!/usr/bin/env python3
"""Generic batch renderer — points at a job folder, renders through MiniMax H3 unattended.

ISOLATION: This renderer is independent of the Equal Shares pipeline. It never
reads or writes outputs/equal_shares/** state files (manifest, story_config,
voice_requirements). The render backend, thermal guard, and model settings are
shared because they are proven and must not be reimplemented.

SOCKET / TAG MAPPING (zero-based sockets, one-based prompt tags):
  ref_images.ref_image_0  ->  <Picture 1>  (img0 slot)
  ref_images.ref_image_1  ->  <Picture 2>  (img1 slot)
  ref_images.ref_image_2  ->  <Picture 3>  (img2 slot)
  ref_videos.ref_video_0  ->  <Video 1>    (video_refs slot, motion only)

Video socket confirmed 2026-08-22 from nodes_minimax_h3.py source:
  MiniMaxH3ReferenceToVideo has ref_videos (Autogrow, io.Image.Input).
  Loaded via core nodes: LoadVideo (output 0) -> GetVideoComponents (output 0 = IMAGE frames).

JOB FOLDER LAYOUT (subfolder form):
  <job>/
    prompts/        0001.txt, 0002.txt ...  one complete H3 prompt per render
    video_refs/     00.mp4, 01.mp4 ...      motion reference (optional slot)
    img0/           character reference (one file = fixed; many = sequential)
    img1/           setting reference
    img2/           second character (optional)
    renders/        created here -- output lands here

  Flat layout also accepted: prompt_001.txt, video_001.mp4, img0_001.png ...

SLOT FILL RULE:
  A slot folder with ONE file  -> that file is used for every render.
  A slot folder with N>1 files -> matched sequentially by natural-sorted prompt index.
  Mismatched counts produce a WARNING and are shown in the plan, not silently truncated.

OPERATOR PROMPT FORMAT:
  Write complete six-section H3 prompts using <Picture N> tags matching the number
  of wired image slots. Do NOT include <Video N> — the renderer injects the motion
  lock in all three required places automatically.

  Optional: first line of a prompt file may be "# duration: 9.5" to override
  the --duration argument for that specific render.
"""
from __future__ import annotations

# Shared production Autogrow helpers (handoff root)
import sys as _sys
from pathlib import Path as _Path
_HANDOFF = _Path(__file__).resolve().parents[1]
if str(_HANDOFF) not in _sys.path:
    _sys.path.insert(0, str(_HANDOFF))
try:
    import gvd_graph_builder as _ggb  # noqa: F401
except Exception:
    _ggb = None

import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).parent))

import thermal_guard
import duration_ladder as dl
from render_single_pass import (
    submit_workflow,
    wait_for_completion,
    find_video_output,
    api_ready,
    frame_count,
    process_exists,
)

# ── Constants — identical to PROVEN_FACTS.md §1 ──────────────────────────────

UNET_REF2VA  = "minimax_h3_ref2va_pruned_nvfp4.safetensors"
CLIP_NAME    = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE_VIDEO    = "minimax_h3_video_vae_fp16.safetensors"
VAE_AUDIO    = "minimax_h3_audio_vae_fp32.safetensors"
DEFAULT_MP   = 0.9
MIN_MP       = 0.4
MP_DROP      = 0.1
DEFAULT_DUR  = 8.0

COMFY_ROOT   = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
API          = "http://127.0.0.1:8188"

# Model paths config lives in the Equal Shares runtime; read-only access is
# intentional — it points to the same ComfyUI model directories that this
# renderer also needs. This is a configuration pointer, not project state.
ES_MODEL_PATHS = ROOT / "outputs" / "equal_shares" / "runtime" / "minimax_model_paths.yaml"

# Queue lock — batch renderer claims this; reads Equal Shares lock read-only
ES_OWNER_LOCK    = ROOT / "outputs" / "equal_shares" / "runtime" / "render_queue_owner.json"
BATCH_OWNER_LOCK = ROOT / "batch_render_queue_owner.json"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

# Slot folder names and their corresponding <Picture N> tag indices
IMG_SLOTS = ["img0", "img1", "img2"]


# ── Logging ───────────────────────────────────────────────────────────────────

def emit(msg: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    try:
        print(line, flush=True)
    except (BrokenPipeError, OSError):
        pass


# ── Natural sort ──────────────────────────────────────────────────────────────

def _nkey(s: str) -> list:
    """Natural sort key: splits on digit runs so '2' < '10'."""
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]


def natural_sorted(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: _nkey(p.name))


# ── Job folder scanner ────────────────────────────────────────────────────────

class SlotFiles:
    """One reference slot (img0, img1, img2, video_refs, prompts)."""

    def __init__(self, name: str, files: list[Path]) -> None:
        self.name = name
        self.files = natural_sorted(files)
        self.fixed = len(self.files) == 1

    def resolve(self, index: int) -> Path | None:
        """Return the file for render `index` (0-based), or None if slot empty."""
        if not self.files:
            return None
        if self.fixed:
            return self.files[0]
        return self.files[index] if index < len(self.files) else None

    def __len__(self) -> int:
        return len(self.files)

    def __bool__(self) -> bool:
        return bool(self.files)


class JobScan:
    prompts:    SlotFiles
    video_refs: SlotFiles
    img_slots:  list[SlotFiles]   # index 0=img0, 1=img1, 2=img2
    render_count: int
    warnings:   list[str]

    def __init__(self) -> None:
        self.warnings = []


def _collect(folder: Path, exts: set[str]) -> list[Path]:
    return [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in exts]


def scan_job(job: Path) -> JobScan:
    """Detect subfolder or flat layout and return a complete scan."""
    scan = JobScan()

    # ── Subfolder layout ──────────────────────────────────────────────────────
    if (job / "prompts").is_dir():
        prompts_dir   = job / "prompts"
        video_dir     = job / "video_refs"
        img_dirs      = [job / s for s in IMG_SLOTS]

        scan.prompts    = SlotFiles("prompts",    _collect(prompts_dir, {".txt"}))
        scan.video_refs = SlotFiles("video_refs", _collect(video_dir, VIDEO_EXTS) if video_dir.is_dir() else [])
        scan.img_slots  = [SlotFiles(s, _collect(d, IMAGE_EXTS) if d.is_dir() else [])
                           for s, d in zip(IMG_SLOTS, img_dirs)]

    else:
        # ── Flat layout: prompt_N.txt / video_N.mp4 / img0_N.png ─────────────
        def _flat(prefix: str, exts: set[str]) -> list[Path]:
            return [p for p in job.iterdir()
                    if p.is_file()
                    and p.suffix.lower() in exts
                    and (p.stem.startswith(prefix + "_") or p.stem == prefix)]

        scan.prompts    = SlotFiles("prompts",    _flat("prompt",    {".txt"}))
        scan.video_refs = SlotFiles("video_refs", _flat("video",     VIDEO_EXTS))
        scan.img_slots  = [SlotFiles(s, _flat(s, IMAGE_EXTS)) for s in IMG_SLOTS]

    n = len(scan.prompts)
    scan.render_count = n

    # ── Slot count validation ─────────────────────────────────────────────────
    for slot in [scan.video_refs] + scan.img_slots:
        if not slot or slot.fixed:
            continue
        if len(slot) != n:
            scan.warnings.append(
                f"WARNING: {slot.name} has {len(slot)} files but prompts has {n}. "
                f"Renders beyond position {len(slot)-1} will get no {slot.name}."
            )

    return scan


def build_render_plan(scan: JobScan, job: Path, megapixels: float,
                      default_duration: float) -> list[dict]:
    """Return one dict per render describing everything that will happen."""
    renders = []
    for i in range(scan.render_count):
        prompt_path = scan.prompts.resolve(i)
        video_path  = scan.video_refs.resolve(i) if scan.video_refs else None
        img_paths   = [slot.resolve(i) for slot in scan.img_slots]

        # Determine which image slots are actually wired
        wired_images = [p for p in img_paths if p is not None]
        image_count  = len(wired_images)
        has_video    = video_path is not None

        # Resolve prompt tags (one-based, contiguous per wired refs)
        picture_tags = [f"<Picture {j+1}>" for j in range(image_count)]
        video_tag    = "<Video 1>" if has_video else None

        # Read duration from prompt file header or use default
        duration = default_duration
        if prompt_path and prompt_path.is_file():
            first = prompt_path.read_text(encoding="utf-8").splitlines()
            if first and first[0].strip().startswith("# duration:"):
                try:
                    duration = float(first[0].split(":", 1)[1].strip())
                except ValueError:
                    pass

        frames = frame_count(duration)
        output_stem = f"{i+1:04d}"
        out_path = job / "renders" / f"{output_stem}_00001.mp4"

        renders.append({
            "index":        i,
            "prompt_path":  prompt_path,
            "video_path":   video_path,
            "img_paths":    wired_images,
            "image_count":  image_count,
            "has_video":    has_video,
            "picture_tags": picture_tags,
            "video_tag":    video_tag,
            "duration":     duration,
            "frames":       frames,
            "megapixels":   megapixels,
            "out_path":     out_path,
        })
    return renders


def print_plan(renders: list[dict], warnings: list[str]) -> None:
    print("\n=== BATCH RENDER PLAN ===")
    for w in warnings:
        print(w)
    if warnings:
        print()
    for r in renders:
        print(f"Render {r['index']+1:>3}/{len(renders)}")
        print(f"  prompt:   {r['prompt_path']}")
        print(f"  video:    {r['video_path'] or '(none)'}")
        for j, p in enumerate(r["img_paths"]):
            print(f"  img{j}:     {p}  -> {r['picture_tags'][j]}")
        print(f"  tags:     {' '.join(r['picture_tags'])}" +
              (f" {r['video_tag']}" if r['video_tag'] else ""))
        print(f"  duration: {r['duration']:.1f}s  frames: {r['frames']}")
        print(f"  mp:       {r['megapixels']}")
        print(f"  output:   {r['out_path']}")
    print("=========================\n")


# ── Motion-lock prompt assembly ───────────────────────────────────────────────

_VIDEO_SUBJECT_LINE = (
    "<Video 1> provides motion and camera pacing reference for this clip; "
    "no visual content from it is reproduced in the target video."
)

_VIDEO_RETENTION_LINE = (
    "<Video 1> (motion and camera structure only): weak_reference - only the "
    "movement, timing, and camera behaviour are taken from <Video 1>. None of "
    "its people, faces, bodies, clothing, setting, or lighting appear in the "
    "target video."
)

_VIDEO_DD_SENTENCE = (
    "The motion and camera timing of the clip follow the rhythm of <Video 1>, "
    "but none of <Video 1>'s people, faces, clothing, setting, or lighting "
    "appear; character appearance is determined entirely by the reference images."
)


def _inject_into_section(text: str, section: str, content: str,
                          append: bool = True) -> str:
    """Append or prepend `content` inside `section:` block of the H3 prompt."""
    pattern = rf"(^{re.escape(section)}\s*\n)(.*?)(?=^\w[\w_]*:\s*$|\Z)"
    def replacer(m):
        header = m.group(1)
        body   = m.group(2)
        if append:
            return header + body.rstrip() + "\n" + content + "\n"
        else:
            return header + content + "\n" + body
    return re.sub(pattern, replacer, text, flags=re.M | re.S)


def assemble_prompt(text: str, image_count: int, has_video: bool) -> str:
    """Inject video motion lock into an operator-written prompt.

    The operator's prompt must:
    - Be a complete six-section H3 prompt
    - Use <Picture N> tags matching the number of wired image slots
    - NOT include <Video N> tags (those are injected here)

    Three injections are made when has_video is True:
    1. subject_definitions: standalone <Video 1> definition appended
    2. retention_analysis: <Video 1> weak_reference line appended
    3. detailed_description: confirming sentence prepended (before [Shot 1])
    """
    if not has_video:
        return text

    # Strip per-file duration header if present (validator would fail on it)
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("# duration:"):
        text = "\n".join(lines[1:]).lstrip()

    # 1. subject_definitions — append <Video 1> standalone entry
    text = _inject_into_section(text, "subject_definitions:", _VIDEO_SUBJECT_LINE, append=True)

    # 2. retention_analysis — append <Video 1> line
    text = _inject_into_section(text, "retention_analysis:", _VIDEO_RETENTION_LINE, append=True)

    # 3. detailed_description — prepend confirming sentence before [Shot 1]
    #    Insert after the style-opener line (the sentence before [Shot 1])
    def inject_before_shot1(m):
        header = m.group(1)
        body   = m.group(2)
        # If there's a style opener (text before [Shot 1]), inject after it
        shot1 = re.search(r"^\[Shot 1\]", body, re.M)
        if shot1:
            pre  = body[:shot1.start()].rstrip()
            rest = body[shot1.start():]
            return header + pre + "\n" + _VIDEO_DD_SENTENCE + "\n" + rest
        # No [Shot 1] found — prepend at top of section
        return header + _VIDEO_DD_SENTENCE + "\n" + body

    text = re.sub(
        r"(^detailed_description:\s*\n)(.*?)(?=^\w[\w_]*:\s*$|\Z)",
        inject_before_shot1,
        text,
        flags=re.M | re.S,
    )

    return text


def validate_assembled_prompt(text: str, image_count: int,
                              has_video: bool, prompt_name: str) -> list[str]:
    """Run the H3 validator and check image tag count. Returns list of errors."""
    sys.path.insert(0, str(ROOT / "local_agent"))
    from validate_h3_prompt import validate

    report = validate(text, prompt_name, expect_audio=0)
    errors = list(report.errors)

    # Count <Picture N> tags declared in subject_definitions
    defs_m = re.search(r"^subject_definitions:\s*$(.*?)(?=^\w[\w_]*:\s*$|\Z)",
                       text, re.M | re.S)
    defs = defs_m.group(1) if defs_m else ""
    declared_pics = sorted({int(x) for x in re.findall(r"<Picture (\d+)>", defs)})
    expected_pics = list(range(1, image_count + 1))
    if declared_pics != expected_pics:
        errors.append(
            f"PICTURE_MISMATCH: prompt declares <Picture {declared_pics}> but "
            f"{image_count} image(s) are wired (expected {expected_pics}). "
            f"Tags must match sockets exactly."
        )

    return errors


# ── ComfyUI setup — adapted from render_single_pass for the batch context ─────

def _ensure_in_input(src: Path, input_dir: Path, dst_name: str) -> str:
    """Copy src to ComfyUI input dir. Returns the filename (not full path)."""
    input_dir.mkdir(parents=True, exist_ok=True)
    dst = input_dir / dst_name
    if not dst.exists():
        shutil.copy2(src, dst)
    return dst_name


def _find_job_video(outputs: dict, output_dir: Path) -> str | None:
    """2026-09-29ai: the SaveVideo mp4 in THIS job's ComfyUI --output-directory (core SaveVideo reports it under
    "images"), else render_single_pass.find_video_output's ComfyUI-Shared/output lookup."""
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        for key in ("video", "videos", "gifs", "images"):
            items = node_out.get(key, [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                fname = item.get("filename", "")
                if fname and Path(fname).suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"}:
                    sub = item.get("subfolder", "")
                    p = Path(output_dir) / sub / fname if sub else Path(output_dir) / fname
                    if p.exists():
                        return str(p)
    return find_video_output(outputs)


def start_comfy_batch(log_dir: Path, input_dir: Path, output_dir: Path,
                      user_dir: Path, temp_dir: Path) -> int:
    """Start ComfyUI for the batch renderer. Returns the process pid."""
    for d in (input_dir, output_dir, user_dir, temp_dir, log_dir):
        d.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stdout = (log_dir / f"comfy_batch_{stamp}.stdout.log").open("ab")
    stderr = (log_dir / f"comfy_batch_{stamp}.stderr.log").open("ab")

    args = [
        str(COMFY_PYTHON), "main.py",
        "--listen", "127.0.0.1", "--port", "8188",
        "--disable-auto-launch",
        "--output-directory", str(output_dir),
        "--input-directory",  str(input_dir),
        "--user-directory",   str(user_dir),
        "--temp-directory",   str(temp_dir),
        "--disable-all-custom-nodes",
        "--use-sage-attention",
        # 2026-09-29ai (16 GB agent RAM cap, CLAUDE.md 29r; residency relaxed 29af): as shipped, only
        # --use-sage-attention rose >= 18.0 GB at 0.9 MP (29z, free RAM 0.71 GB). The GVD MiniMax runner family's
        # flags keep the dynamic loader's weight copies disk-backed (--fast-disk), nothing in pinned RAM, the text
        # encoder released after the encode, and no Windows VRAM reserve; measured at this renderer's 0.9 MP default
        # in CHANGELOG 29ai (weights stream during sampling, which 29af allows; the whole job stays under the cap).
        "--fast-disk", "--disable-pinned-memory", "--cache-none", "--reserve-vram", "0",
    ]
    if ES_MODEL_PATHS.is_file():
        args += ["--extra-model-paths-config", str(ES_MODEL_PATHS)]

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(args, cwd=COMFY_ROOT, stdout=stdout, stderr=stderr,
                            creationflags=flags, env=env)
    emit(f"Started ComfyUI pid={proc.pid}")

    for _ in range(90):
        if api_ready():
            emit("ComfyUI API ready")
            return proc.pid
        if proc.poll() is not None:
            raise RuntimeError(f"ComfyUI exited during startup rc={proc.returncode}")
        time.sleep(5)
    raise TimeoutError("ComfyUI did not become ready within 450 s")


def stop_comfy_batch(comfy_pid: int | None) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{API}/interrupt", data=b"{}",
                                   headers={"Content-Type": "application/json"},
                                   method="POST"),
            timeout=5,
        ).read()
    except Exception:
        pass
    time.sleep(2)
    if comfy_pid:
        cmd = f"Stop-Process -Id {comfy_pid} -Force -ErrorAction SilentlyContinue"
    else:
        cur = os.getpid()
        cmd = (
            f"Get-Process | Where-Object {{ $_.ProcessName -eq 'python' -and "
            f"$_.Path -like '{COMFY_ROOT}\\*' -and $_.Id -ne {cur} }} "
            f"| Stop-Process -Force"
        )
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
    for _ in range(20):
        if not api_ready():
            emit("ComfyUI stopped; GPU cleared")
            return
        time.sleep(1)
    emit("WARNING: ComfyUI did not stop cleanly within 20 s")


# ── Queue ownership ───────────────────────────────────────────────────────────

def _pid_live(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True,
    )
    return r.returncode == 0


def claim_queue() -> bool:
    # Block if Equal Shares pass is live (read-only check)
    if ES_OWNER_LOCK.exists():
        try:
            owner = json.loads(ES_OWNER_LOCK.read_text(encoding="utf-8-sig"))
            if _pid_live(int(owner.get("pid", 0))):
                emit(f"Equal Shares pass is live (pid={owner['pid']}); cannot start batch.")
                return False
        except Exception:
            pass

    # Block if another batch is live
    if BATCH_OWNER_LOCK.exists():
        try:
            owner = json.loads(BATCH_OWNER_LOCK.read_text(encoding="utf-8-sig"))
            if owner.get("pid") != os.getpid() and _pid_live(int(owner.get("pid", 0))):
                emit(f"Another batch render is live (pid={owner['pid']}); cannot start.")
                return False
        except Exception:
            pass

    BATCH_OWNER_LOCK.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "batch render — batch_render_folder.py",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    BATCH_OWNER_LOCK.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


# ── Workflow builder ──────────────────────────────────────────────────────────

def build_batch_workflow(
    image_filenames: list[str],
    video_filename:  str | None,
    prompt_text:     str,
    duration:        float,
    seed:            int,
    out_prefix:      str,
    megapixels:      float = DEFAULT_MP,
    audio_filenames: list[str] | None = None,
    character_ids_for_audio: list[str] | None = None,
) -> dict:
    """Build a ref2va ComfyUI API workflow for the batch renderer.

    Uses core ComfyUI nodes only (--disable-all-custom-nodes is set).
    Video loading: LoadVideo -> GetVideoComponents -> output 0 (IMAGE frames).

    SOCKET MAP (zero-based) -> PROMPT TAG (one-based):
      ref_images.ref_image_0  ->  <Picture 1>
      ref_images.ref_image_1  ->  <Picture 2>
      ref_images.ref_image_2  ->  <Picture 3>
      ref_videos.ref_video_0  ->  <Video 1>   (motion only, no audio paired)
      ref_audios.ref_audio_0  ->  <Audio 1>   (voice identity; map to character_id)
    """
    wf: dict = {}

    # Resolution
    wf["115"] = {"class_type": "ResolutionSelector", "inputs": {
        "aspect_ratio": "16:9 (Widescreen)",
        "megapixels":   megapixels,
        "multiple":     32,
    }}

    # VAEs
    wf["119"] = {"class_type": "VAELoader",   "inputs": {"vae_name": VAE_VIDEO}}
    wf["120"] = {"class_type": "VAELoader",   "inputs": {"vae_name": VAE_AUDIO}}

    # Model + encoder
    wf["127"] = {"class_type": "UNETLoader",  "inputs": {
        "unet_name": UNET_REF2VA, "weight_dtype": "default"}}
    wf["128"] = {"class_type": "CLIPLoader",  "inputs": {
        "clip_name": CLIP_NAME, "type": "minimax", "device": "default"}}

    # Duration -> frames
    wf["132"] = {"class_type": "PrimitiveFloat",    "inputs": {"value": duration}}
    wf["131"] = {"class_type": "ComfyMathExpression", "inputs": {
        "expression": "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17",
        "values.a": ["132", 0],
    }}

    # Prompt
    wf["138"] = {"class_type": "PrimitiveStringMultiline", "inputs": {"value": prompt_text}}

    # Sampler chain
    wf["129"] = {"class_type": "RandomNoise",       "inputs": {"noise_seed": seed}}
    wf["123"] = {"class_type": "KSamplerSelect",    "inputs": {"sampler_name": "res_multistep"}}
    wf["124"] = {"class_type": "BasicScheduler",    "inputs": {
        "scheduler": "simple", "steps": 20, "denoise": 1.0, "model": ["127", 0]}}

    # Reference node inputs
    ref_inputs: dict = {
        "prompt":        ["138", 0],
        "width":         ["115", 0],
        "height":        ["115", 1],
        "length":        ["131", 1],
        "ref_image_size": "match",
        "clip":          ["128", 0],
        "vae":           ["119", 0],
        "audio_vae":     ["120", 0],
    }

    # Image slots (zero-based socket, one-based tag)
    for i, img_fname in enumerate(image_filenames):
        img_node = f"300_{i}"
        wf[img_node] = {"class_type": "LoadImage", "inputs": {"image": img_fname}}
        ref_inputs[f"ref_images.ref_image_{i}"] = [img_node, 0]

    # Audio slots (zero-based socket -> <Audio N+1>); voice identity only
    audio_filenames = list(audio_filenames or [])
    if len(audio_filenames) > 3:
        raise ValueError(
            f"{len(audio_filenames)} audio refs exceed MiniMax max 3; split/replan shot"
        )
    for i, aud_fname in enumerate(audio_filenames):
        aud_node = f"310_{i}"
        wf[aud_node] = {"class_type": "LoadAudio", "inputs": {"audio": aud_fname}}
        ref_inputs[f"ref_audios.ref_audio_{i}"] = [aud_node, 0]
    # Optional character mapping note for prompt authors / callers
    if character_ids_for_audio:
        if len(character_ids_for_audio) != len(audio_filenames):
            raise ValueError("character_ids_for_audio length must match audio_filenames")

    # Video slot (socket ref_videos.ref_video_0 -> <Video 1>)
    # Core pipeline: LoadVideo -> GetVideoComponents -> output 0 (IMAGE frames)
    if video_filename is not None:
        wf["400"] = {"class_type": "LoadVideo",         "inputs": {"file": video_filename}}
        wf["401"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["400", 0]}}
        ref_inputs["ref_videos.ref_video_0"] = ["401", 0]

    # MiniMaxH3ReferenceToVideo
    wf["136"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": ref_inputs}

    # Guider + sampler
    wf["126"] = {"class_type": "BasicGuider", "inputs": {
        "model": ["127", 0], "conditioning": ["136", 0]}}
    wf["125"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["129", 0], "guider": ["126", 0],
        "sampler": ["123", 0], "sigmas": ["124", 0],
        "latent_image": ["136", 1],
    }}

    # Decode
    wf["122"] = {"class_type": "VAEDecode",      "inputs": {
        "samples": ["125", 0], "vae": ["119", 0]}}
    wf["121"] = {"class_type": "VAEDecodeAudio", "inputs": {
        "samples": ["125", 0], "vae": ["120", 0]}}
    wf["130"] = {"class_type": "CreateVideo",    "inputs": {
        "fps": 24.0, "bit_depth": 8,
        "images": ["122", 0], "audio": ["121", 0],
    }}

    # Save
    wf["92"] = {"class_type": "SaveVideo", "inputs": {
        "filename_prefix": out_prefix,
        "format": "auto",
        "codec":  "auto",
        "video":  ["130", 0],
    }}

    return wf


# ── Manifest ──────────────────────────────────────────────────────────────────

def load_manifest(job: Path) -> dict:
    p = job / "batch_manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"job": str(job), "created": datetime.now().isoformat(timespec="seconds"),
            "renders": {}}


def save_manifest(job: Path, data: dict) -> None:
    p = job / "batch_manifest.json"
    tmp = p.with_name(f"batch_manifest.tmp.{os.getpid()}.json")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _record(manifest: dict, key: str, entry: dict) -> None:
    prev = manifest["renders"].get(key)
    e = dict(entry)
    if prev:
        history = list(prev.get("attempt_history", []))
        history.append({k: v for k, v in prev.items() if k != "attempt_history"})
        e["attempt_history"] = history
    manifest["renders"][key] = e


# ── Main render loop ──────────────────────────────────────────────────────────

def render_batch(job: Path, limit: int | None, force: bool,
                 megapixels: float, default_duration: float,
                 dry_run: bool) -> int:
    scan = scan_job(job)
    if not scan.prompts:
        emit(f"No prompt files found in {job}")
        return 1

    renders = build_render_plan(scan, job, megapixels, default_duration)
    print_plan(renders, scan.warnings)

    if dry_run:
        emit("Dry run — stopping before render.")
        return 0

    (job / "renders").mkdir(parents=True, exist_ok=True)

    # ComfyUI runtime dirs inside the job folder to stay isolated
    runtime   = job / "batch_runtime"
    input_dir = runtime / "input"
    out_dir   = runtime / "output"
    user_dir  = runtime / "user"
    temp_dir  = runtime / "temp"
    log_dir   = runtime / "logs"

    if not claim_queue():
        return 3

    manifest    = load_manifest(job)
    comfy_pid: int | None = None
    rendered    = 0
    limited     = limit or len(renders)

    try:
        for r in renders:
            if rendered >= limited:
                emit(f"Reached --limit {limited}; stopping.")
                break

            key = f"{r['index']+1:04d}"

            # Skip already-done renders unless --force
            prev = manifest["renders"].get(key, {})
            if not force and prev.get("status") == "done":
                out = Path(prev.get("output_path", ""))
                if out.exists():
                    emit(f"[{key}] already done — skip ({out})")
                    continue

            # Read and assemble prompt
            prompt_path: Path = r["prompt_path"]
            if not prompt_path or not prompt_path.is_file():
                emit(f"[{key}] MISSING prompt file: {prompt_path}")
                _record(manifest, key, {"status": "error", "error": "missing prompt"})
                save_manifest(job, manifest)
                continue

            raw_text = prompt_path.read_text(encoding="utf-8").strip()
            assembled = assemble_prompt(raw_text, r["image_count"], r["has_video"])

            # Validate assembled prompt
            errs = validate_assembled_prompt(
                assembled, r["image_count"], r["has_video"], prompt_path.name)
            if errs:
                emit(f"[{key}] INVALID prompt — skipping:")
                for e in errs:
                    emit(f"  {e}")
                _record(manifest, key, {"status": "invalid", "errors": errs})
                save_manifest(job, manifest)
                continue

            # Copy reference files to ComfyUI input dir
            img_fnames: list[str] = []
            for j, img_path in enumerate(r["img_paths"]):
                dst_name = f"batch_{key}_img{j}{img_path.suffix}"
                try:
                    _ensure_in_input(img_path, input_dir, dst_name)
                    img_fnames.append(dst_name)
                except Exception as e:
                    emit(f"[{key}] MISSING image {img_path}: {e}")
                    _record(manifest, key, {"status": "error", "error": str(e)})
                    save_manifest(job, manifest)
                    break
            else:
                # Successful image copy — continue to video
                vid_fname: str | None = None
                if r["video_path"]:
                    dst_name = f"batch_{key}_video{r['video_path'].suffix}"
                    try:
                        _ensure_in_input(r["video_path"], input_dir, dst_name)
                        vid_fname = dst_name
                    except Exception as e:
                        emit(f"[{key}] MISSING video {r['video_path']}: {e}")
                        _record(manifest, key, {"status": "error", "error": str(e)})
                        save_manifest(job, manifest)
                        continue

                seed       = random.randint(0, 2 ** 53)
                cur_mp     = r["megapixels"]
                cur_dur    = r["duration"]
                has_dialogue = bool(re.search(r"<d>", assembled))
                out_prefix = f"batch_{key}"
                success    = False

                # Determine retry strategy
                if has_dialogue:
                    ladder = dl.ladder(cur_dur)
                else:
                    ladder = [{"seconds": cur_dur, "frames": frame_count(cur_dur)}]
                    # One retry with same duration
                    ladder.append(ladder[0])

                attempt = 0
                while not success and cur_mp >= MIN_MP:
                    rung_dur = ladder[min(attempt, len(ladder)-1)]["seconds"]

                    thermal_guard.wait_before_render(emit)

                    if api_ready():
                        stop_comfy_batch(comfy_pid)
                        comfy_pid = None
                    ram_base = _ram_used_gb()  # 2026-10-02z: before the backend, like the GVD runner
                    comfy_pid = start_comfy_batch(log_dir, input_dir, out_dir,
                                                   user_dir, temp_dir)

                    wf = build_batch_workflow(
                        img_fnames, vid_fname, assembled,
                        rung_dur, seed, out_prefix, cur_mp)

                    try:
                        prompt_id = submit_workflow(wf)
                        emit(f"[{key}] submitted prompt_id={prompt_id} "
                             f"dur={rung_dur:.1f}s mp={cur_mp}")
                        outputs, ram_mon = _wait_with_ram_cap(prompt_id, key, ram_base)  # 2026-10-02z
                        vid_out = _find_job_video(outputs, out_dir)  # 2026-09-29ai

                        if vid_out:
                            # Move to renders/; never overwrite — add attempt suffix
                            dest = _next_output_path(job / "renders", key, attempt)
                            shutil.move(vid_out, dest)
                            emit(f"[{key}] DONE -> {dest}")
                            _record(manifest, key, {
                                "status":      "done",
                                "output_path": str(dest),
                                "prompt_path": str(prompt_path),
                                "img_paths":   [str(p) for p in r["img_paths"]],
                                "video_path":  str(r["video_path"]) if r["video_path"] else None,
                                "seed":        seed,
                                "duration":    rung_dur,
                                "frames":      frame_count(rung_dur),
                                "megapixels":  cur_mp,
                                "attempt":     attempt + 1,
                                "rendered_at": datetime.now().isoformat(timespec="seconds"),
                                "ram_rise_gb_peak": ram_mon.get("ram_rise_gb_peak"),  # 2026-10-02z
                            })
                            save_manifest(job, manifest)
                            success = True
                            rendered += 1
                        else:
                            raise RuntimeError(f"No video in outputs: {list(outputs.keys())}")

                    except RamCapExceeded as e:  # 2026-10-02z: a stop-and-hand-off, never retried as is
                        emit(f"[{key}] {e} - not retried")
                        _record(manifest, key, {"status": "failed", "error": f"RAM cap: {e}"})
                        save_manifest(job, manifest)
                        break
                    except thermal_guard.ThermalLimitExceeded:
                        emit(f"[{key}] thermal stop — cooling before next attempt")
                        thermal_guard.wait_after_render(emit)
                        attempt += 1
                    except Exception as e:
                        emit(f"[{key}] attempt {attempt+1} failed: {e}")
                        if "VRAM" in str(e) or "out of memory" in str(e).lower():
                            new_mp = round(cur_mp - MP_DROP, 1)
                            if new_mp < MIN_MP:
                                emit(f"[{key}] VRAM floor reached at {MIN_MP} MP — skipping")
                                _record(manifest, key, {
                                    "status": "failed",
                                    "error": f"VRAM floor: {str(e)[:120]}",
                                })
                                save_manifest(job, manifest)
                                break
                            emit(f"[{key}] VRAM error — dropping to {new_mp} MP")
                            cur_mp = new_mp
                        attempt += 1
                        if not has_dialogue and attempt >= 2:
                            emit(f"[{key}] two attempts failed — skipping")
                            _record(manifest, key, {
                                "status": "failed",
                                "error": f"2 attempts failed: {str(e)[:120]}",
                            })
                            save_manifest(job, manifest)
                            break

                    if api_ready():
                        stop_comfy_batch(comfy_pid)
                        comfy_pid = None
                    thermal_guard.wait_after_render(emit)

                continue  # outer for-loop iteration (skips the else on the image-copy loop)

            # If we broke out of the image-copy loop
            continue

    finally:
        if api_ready():
            stop_comfy_batch(comfy_pid)
        release_queue()

    manifest = load_manifest(job)
    done  = sum(1 for v in manifest["renders"].values() if v.get("status") == "done")
    total = len(renders)
    emit(f"Batch complete: {done}/{total} renders done")
    return 0 if done == min(total, limited) else 1


# 2026-10-02z (TODO since 29ai): the agent's own RAM rise is capped at 16 GB (CLAUDE.md 29r). The GVD runner has
# interrupted a live render that crosses it since 29s; this renderer only had the thermal guard. Same Monitor, same cap.
class RamCapExceeded(RuntimeError):
    pass


def _ram_used_gb() -> float:
    import psutil
    return psutil.virtual_memory().used / 2**30


def _ram_cap_monitor(baseline_used_gb: float):
    sys.path.insert(0, str(ROOT / "local_agent"))
    from gvd_tool_router.runner import Monitor
    return Monitor(API, thermal_guard, baseline_used_gb=baseline_used_gb)


def _wait_with_ram_cap(prompt_id: str, key: str, baseline_used_gb: float) -> tuple[dict, dict]:
    """wait_for_completion under the runner's Monitor; RamCapExceeded when the Monitor interrupted on the cap."""
    mon = _ram_cap_monitor(baseline_used_gb)
    try:
        with mon:
            outputs = wait_for_completion(prompt_id, key)
    except Exception:
        if getattr(mon, "cap_tripped", False):
            s = mon.summary()
            raise RamCapExceeded(f"RAM rise {s.get('ram_rise_gb_peak')} GB crossed the {s.get('ram_cap_gb')} GB "
                                 "agent cap; the render was interrupted") from None
        raise
    if getattr(mon, "cap_tripped", False):
        s = mon.summary()
        raise RamCapExceeded(f"RAM rise {s.get('ram_rise_gb_peak')} GB crossed the {s.get('ram_cap_gb')} GB "
                             "agent cap; the render was interrupted")
    return outputs, mon.summary()


def _next_output_path(renders_dir: Path, key: str, attempt: int) -> Path:
    """Return a unique path in renders_dir, never overwriting."""
    suffix = f"_attempt{attempt+1}" if attempt > 0 else ""
    base = renders_dir / f"{key}{suffix}.mp4"
    if not base.exists():
        return base
    n = 2
    while True:
        p = renders_dir / f"{key}{suffix}_{n:05d}.mp4"
        if not p.exists():
            return p
        n += 1


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Batch-render a job folder through MiniMax H3.")
    ap.add_argument("folder",    help="Job folder path")
    ap.add_argument("--plan",    action="store_true",
                    help="Print the render plan and exit (no GPU)")
    ap.add_argument("--limit",   type=int, default=None, metavar="N",
                    help="Stop after N renders (operator preview)")
    ap.add_argument("--force",   action="store_true",
                    help="Re-render even if output already exists")
    ap.add_argument("--megapixels", type=float, default=DEFAULT_MP, metavar="MP",
                    help=f"Starting megapixels (default {DEFAULT_MP}; drops on VRAM error)")
    ap.add_argument("--duration",   type=float, default=DEFAULT_DUR, metavar="S",
                    help=f"Default duration in seconds (default {DEFAULT_DUR}; "
                         f"overridden per-file with '# duration: N' header)")
    args = ap.parse_args()

    job = Path(args.folder).resolve()
    if not job.is_dir():
        print(f"ERROR: {job} is not a directory", file=sys.stderr)
        return 1

    return render_batch(
        job=job,
        limit=args.limit,
        force=args.force,
        megapixels=args.megapixels,
        default_duration=args.duration,
        dry_run=args.plan,
    )


if __name__ == "__main__":
    raise SystemExit(main())
