#!/usr/bin/env python3
"""Single-pass 0.9 MP render supervisor — Equal Shares.

Task 0 passed. Renders all 124 clips at 1280×736:
  - 78 dialogue clips: ref2va + audio ref from audio_pass_config.json
  - 46 non-dialogue clips: fl2va using story_config.json prompts

Progress is tracked in outputs/equal_shares/single_pass_manifest.json.
Run alongside Task 4 (dialogue audit); this script owns the GPU.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

import thermal_guard

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
AUDIO_CFG = PROJECT / "audio_pass_config.json"
STORY_CFG = PROJECT / "story_config.json"
MANIFEST = PROJECT / "single_pass_manifest.json"
LOG = PROJECT / "runtime" / "single_pass_supervisor.log"
OWNER_LOCK = PROJECT / "runtime" / "render_queue_owner.json"

COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
MODEL_PATHS = PROJECT / "runtime" / "minimax_model_paths.yaml"
COMFY_RUNTIME = PROJECT / "runtime" / "codex_comfy_runtime"
SHARED_INPUT = COMFY_RUNTIME / "input"
SHARED_OUTPUT = COMFY_RUNTIME / "output"
COMFY_USER = COMFY_RUNTIME / "user"
COMFY_TEMP = COMFY_RUNTIME / "temp"
LEGACY_SHARED_OUTPUT = Path(r"A:\Users\rhine\ComfyUI-Shared\output")

API = "http://127.0.0.1:8188"

UNET_REF2VA = "minimax_h3_ref2va_pruned_nvfp4.safetensors"
UNET_FL2VA = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
CLIP_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE_VIDEO = "minimax_h3_video_vae_fp16.safetensors"
VAE_AUDIO = "minimax_h3_audio_vae_fp32.safetensors"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
EXPECTED_WIDTH = 1280
EXPECTED_HEIGHT = 736


# ── Logging ──────────────────────────────────────────────────────────────────

def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    try:
        print(line, flush=True)
    except (BrokenPipeError, OSError):
        pass
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


# ── Queue ownership ───────────────────────────────────────────────────────────

def process_exists(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True,
    )
    return r.returncode == 0


def claim_queue() -> bool:
    if OWNER_LOCK.exists():
        try:
            owner = json.loads(OWNER_LOCK.read_text(encoding="utf-8-sig"))
            owner_pid = int(owner.get("pid", 0))
        except Exception:
            owner_pid = 0
        if owner_pid != os.getpid() and process_exists(owner_pid):
            emit(f"Queue owned by live pid={owner_pid}; cannot claim.")
            return False
    OWNER_LOCK.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "single-pass 0.9 MP render — 124 clips, Task 0 branch, Claude Code agent",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    OWNER_LOCK.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released",
    }, indent=2), encoding="utf-8")


# ── ComfyUI lifecycle ─────────────────────────────────────────────────────────

def api_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/system_stats", timeout=5):
            return True
    except Exception:
        return False


def start_comfy() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    for directory in (SHARED_INPUT, SHARED_OUTPUT, COMFY_USER, COMFY_TEMP):
        directory.mkdir(parents=True, exist_ok=True)
    stdout = (PROJECT / "runtime" / f"comfy_sp_{stamp}.stdout.log").open("ab")
    stderr = (PROJECT / "runtime" / f"comfy_sp_{stamp}.stderr.log").open("ab")
    args = [
        str(COMFY_PYTHON), "main.py",
        "--listen", "127.0.0.1", "--port", "8188",
        "--disable-auto-launch",
        "--extra-model-paths-config", str(MODEL_PATHS),
        "--output-directory", str(SHARED_OUTPUT),
        "--input-directory", str(SHARED_INPUT),
        "--user-directory", str(COMFY_USER),
        "--temp-directory", str(COMFY_TEMP),
        # Every class used by this API workflow is a ComfyUI core node. Loading
        # the unrelated custom-node tree can hang on import-time pip/install
        # hooks, so keep the render backend minimal and deterministic.
        "--disable-all-custom-nodes",
        "--use-sage-attention",
    ]
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


def stop_comfy(comfy_pid: int | None) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(f"{API}/interrupt", data=b"{}",
                                   headers={"Content-Type": "application/json"}, method="POST"),
            timeout=5).read()
    except Exception:
        pass
    time.sleep(2)
    if comfy_pid:
        cmd = f"Stop-Process -Id {comfy_pid} -Force -ErrorAction SilentlyContinue"
    else:
        cur = os.getpid()
        cmd = (f"Get-Process | Where-Object {{ $_.ProcessName -eq 'python' -and "
               f"$_.Path -like 'A:\\Users\\rhine\\ComfyUI-Installs\\Rockernow\\*' -and "
               f"$_.Id -ne {cur} }} | Stop-Process -Force")
    subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True)
    for _ in range(20):
        if not api_ready():
            emit("ComfyUI stopped; GPU cleared")
            return
        time.sleep(1)
    emit("WARNING: ComfyUI did not stop cleanly within 20 s")


# ── File preparation ──────────────────────────────────────────────────────────

def ensure_frame_in_input(frame_rel: str) -> str:
    """Copy frame to input dir with __ encoding. Returns ComfyUI input filename."""
    SHARED_INPUT.mkdir(parents=True, exist_ok=True)
    encoded = frame_rel.replace("/", "__").replace("\\", "__")
    dst_png = SHARED_INPUT / encoded
    dst_jpg = SHARED_INPUT / encoded.replace(".png", ".jpg")
    if dst_png.exists():
        return encoded
    if dst_jpg.exists():
        return encoded.replace(".png", ".jpg")
    src = PROJECT / frame_rel
    if not src.exists():
        raise FileNotFoundError(f"Boundary frame not found: {src}")
    shutil.copy2(src, dst_png)
    return encoded


def ensure_audio_in_input(wav_rel: str) -> str:
    """Copy voice ref to input dir as <character>_h3_voice_ref.wav. Returns filename."""
    SHARED_INPUT.mkdir(parents=True, exist_ok=True)
    parts = wav_rel.replace("\\", "/").split("/")
    char = parts[1] if len(parts) >= 3 else "unknown"
    fname = f"{char}_h3_voice_ref.wav"
    dst = SHARED_INPUT / fname
    if not dst.exists():
        src = PROJECT / wav_rel
        if not src.exists():
            raise FileNotFoundError(f"Voice ref not found: {src}")
        shutil.copy2(src, dst)
    return fname


# ── Frame count helper ────────────────────────────────────────────────────────

def frame_count(duration: float) -> int:
    raw = max(5, round(duration * 24))
    return raw + (5 - raw % 17) % 17


# ── Workflow builders ─────────────────────────────────────────────────────────

def _common_nodes(unet: str, duration: float, first_frame_file: str,
                  prompt_text: str, seed: int) -> dict:
    """Nodes common to both ref2va and fl2va workflows."""
    return {
        "115": {"class_type": "ResolutionSelector", "inputs": {
            "aspect_ratio": "16:9 (Widescreen)",
            "megapixels": 0.9,
            "multiple": 32,
        }},
        "119": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
        "120": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
        "127": {"class_type": "UNETLoader", "inputs": {
            "unet_name": unet, "weight_dtype": "default",
        }},
        "128": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": CLIP_NAME, "type": "minimax", "device": "default",
        }},
        "132": {"class_type": "PrimitiveFloat", "inputs": {"value": duration}},
        "131": {"class_type": "ComfyMathExpression", "inputs": {
            "expression": "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17",
            "values.a": ["132", 0],
        }},
        "137": {"class_type": "LoadImage", "inputs": {"image": first_frame_file}},
        "138": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": prompt_text}},
        "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "124": {"class_type": "BasicScheduler", "inputs": {
            "scheduler": "simple", "steps": 20, "denoise": 1.0, "model": ["127", 0],
        }},
        "126": {"class_type": "BasicGuider", "inputs": {
            "model": ["127", 0], "conditioning": ["136", 0],
        }},
        "125": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["129", 0], "guider": ["126", 0],
            "sampler": ["123", 0], "sigmas": ["124", 0],
            "latent_image": ["136", 1],
        }},
        "122": {"class_type": "VAEDecode", "inputs": {
            "samples": ["125", 0], "vae": ["119", 0],
        }},
        "121": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["125", 0], "vae": ["120", 0],
        }},
        "130": {"class_type": "CreateVideo", "inputs": {
            "fps": 24.0, "bit_depth": 8,
            "images": ["122", 0], "audio": ["121", 0],
        }},
    }


def build_ref2va_workflow(clip_id: str, duration: float, first_frame_file: str,
                          audio_files: list[str], prompt_text: str,
                          seed: int, out_prefix: str) -> dict:
    wf = _common_nodes(UNET_REF2VA, duration, first_frame_file, prompt_text, seed)
    ref_inputs: dict = {
        "prompt": ["138", 0],
        "width": ["115", 0],
        "height": ["115", 1],
        "length": ["131", 1],
        "ref_image_size": "match",
        "clip": ["128", 0],
        "vae": ["119", 0],
        "audio_vae": ["120", 0],
        "ref_images.ref_image_0": ["137", 0],
    }
    for i, af in enumerate(audio_files):
        anode = f"200_{i}"
        wf[anode] = {"class_type": "LoadAudio", "inputs": {"audio": af}}
        ref_inputs[f"ref_audios.ref_audio_{i}"] = [anode, 0]
    wf["136"] = {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": ref_inputs}
    _add_save_nodes(wf, out_prefix)
    return wf


def build_fl2va_workflow(clip_id: str, duration: float, first_frame_file: str,
                         prompt_text: str, seed: int, out_prefix: str,
                         last_frame_file: str | None = None) -> dict:
    """Plain image-to-video+audio. No reference sockets, no voice conditioning.

    Used for clips whose every speaker is a one-off (operator rule 2026-08-18):
    nothing in them needs to match another clip, so there is nothing to
    reference. See work/classify_voice_requirements.py.

    Shape taken from the one proven fl2va render on this machine, `17.mp4` in the
    good-audio folder, which is clip `01B`. That graph wires BOTH `first_frame`
    and `last_frame`; `last_frame` was missing here, so a clip with a closing
    anchor silently lost it.
    """
    wf = _common_nodes(UNET_FL2VA, duration, first_frame_file, prompt_text, seed)
    inputs = {
        "prompt": ["138", 0],
        "width": ["115", 0],
        "height": ["115", 1],
        "length": ["131", 1],
        "clip": ["128", 0],
        "vae": ["119", 0],
        "first_frame": ["137", 0],
    }
    if last_frame_file:
        wf["139"] = {"class_type": "LoadImage", "inputs": {"image": last_frame_file}}
        inputs["last_frame"] = ["139", 0]
    wf["136"] = {"class_type": "MiniMaxH3ImageToVideo", "inputs": inputs}
    _add_save_nodes(wf, out_prefix)
    return wf


def _add_save_nodes(wf: dict, out_prefix: str) -> None:
    wf["92"] = {"class_type": "SaveVideo", "inputs": {
        "filename_prefix": out_prefix,
        "format": "auto",
        "codec": "auto",
        "video": ["130", 0],
    }}
    wf["142_1"] = {"class_type": "GetVideoComponents", "inputs": {"video": ["92", 0]}}
    wf["142_2"] = {"class_type": "GetImageSize", "inputs": {"image": ["142_1", 0]}}
    wf["142_100"] = {"class_type": "PrimitiveInt", "inputs": {"value": -1}}
    wf["142_99"] = {"class_type": "ComfyMathExpression", "inputs": {
        "expression": "min(max(int(a if a >= 0 else b + a), 0), b - 1)",
        "values.a": ["142_100", 0], "values.b": ["142_2", 2],
    }}
    wf["142_3"] = {"class_type": "ImageFromBatch", "inputs": {
        "batch_index": ["142_99", 1], "length": 1, "image": ["142_1", 0],
    }}
    wf["143"] = {"class_type": "SaveImageAdvanced", "inputs": {
        "filename_prefix": "ComfyUI", "format": "png",
        "format.bit_depth": "8-bit", "format.input_color_space": "sRGB",
        "images": ["142_3", 0],
    }}
    wf["144"] = {"class_type": "PreviewImage", "inputs": {"images": ["143", 0]}}


# ── API helpers ───────────────────────────────────────────────────────────────

def submit_workflow(workflow: dict) -> str:
    body = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/prompt", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read())
    if "error" in resp:
        raise RuntimeError(f"Submit failed: {resp}")
    return resp["prompt_id"]


def wait_for_completion(prompt_id: str, clip_id: str, timeout_s: int = 7200) -> dict:
    start = time.time()
    last_report = start
    while time.time() - start < timeout_s:
        time.sleep(15)
        thermal_guard.check_running_ceiling(emit, clip_id)
        try:
            with urllib.request.urlopen(f"{API}/history/{prompt_id}", timeout=10) as r:
                hist = json.loads(r.read())
            if hist:
                return hist.get(prompt_id, {}).get("outputs", {})
        except Exception:
            pass
        now = time.time()
        if now - last_report >= 60:
            try:
                with urllib.request.urlopen(f"{API}/queue", timeout=5) as r:
                    q = json.loads(r.read())
                running = len(q.get("queue_running", []))
                pending = len(q.get("queue_pending", []))
            except Exception:
                running, pending = -1, -1
            elapsed = now - start
            emit(f"  {clip_id}: {elapsed/60:.1f} min elapsed, running={running} pending={pending}")
            last_report = now
    raise TimeoutError(f"{clip_id}: timed out after {timeout_s//60} min")


def find_video_output(outputs: dict) -> str | None:
    for node_out in outputs.values():
        if not isinstance(node_out, dict):
            continue
        # Core SaveVideo reports its MP4 under the legacy-named ``images``
        # field. Other video nodes use one of the three video-specific keys.
        for key in ("video", "videos", "gifs", "images"):
            items = node_out.get(key, [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                subfolder = item.get("subfolder", "")
                fname = item.get("filename", "")
                if fname and Path(fname).suffix.lower() in VIDEO_EXTENSIONS:
                    p = SHARED_OUTPUT / subfolder / fname if subfolder else SHARED_OUTPUT / fname
                    if p.exists():
                        return str(p)
    return None


def probe_render(path: Path, expected_duration: float) -> tuple[bool, dict]:
    """Mechanically validate a completed single-pass raw without accepting it."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,duration,sample_rate,channels",
        "-of", "json", str(path),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            return False, {"error": proc.stderr.strip() or f"ffprobe rc={proc.returncode}"}
        data = json.loads(proc.stdout)
        streams = data.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), None)
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        duration = float(data.get("format", {}).get("duration") or (video or {}).get("duration") or 0)
        expected = frame_count(expected_duration) / 24.0
        size = int(data.get("format", {}).get("size") or path.stat().st_size)
        meta = {
            "width": int((video or {}).get("width") or 0),
            "height": int((video or {}).get("height") or 0),
            "fps": (video or {}).get("r_frame_rate"),
            "duration": duration,
            "expected_duration": expected,
            "video_codec": (video or {}).get("codec_name"),
            "audio_codec": (audio or {}).get("codec_name"),
            "audio_sample_rate": (audio or {}).get("sample_rate"),
            "audio_channels": (audio or {}).get("channels"),
            "size": size,
        }
        valid = bool(
            video and audio
            and meta["width"] == EXPECTED_WIDTH
            and meta["height"] == EXPECTED_HEIGHT
            and meta["fps"] == "24/1"
            and abs(duration - expected) <= 0.35
            and size > 0
        )
        return valid, meta
    except Exception as exc:
        return False, {"error": str(exc)}


def find_existing_valid_render(clip_id: str, expected_duration: float) -> tuple[Path | None, dict]:
    """Salvage a finished raw after a state/parser failure; never alter the raw."""
    output_dirs = [
        SHARED_OUTPUT / "story" / f"SP_{clip_id}",
        LEGACY_SHARED_OUTPUT / "story" / f"SP_{clip_id}",
    ]
    candidates = []
    for output_dir in output_dirs:
        if output_dir.exists():
            candidates.extend(output_dir.glob("*.mp4"))
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)
    last_probe: dict = {}
    for path in candidates:
        valid, probe = probe_render(path, expected_duration)
        if valid:
            return path, probe
        last_probe = probe
    return None, last_probe


# ── Manifest helpers ──────────────────────────────────────────────────────────

def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"clips": {}, "created": datetime.now().isoformat(timespec="seconds")}


def save_manifest(data: dict) -> None:
    temp = MANIFEST.with_name(f"{MANIFEST.name}.tmp.{os.getpid()}")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, MANIFEST)


def record_clip_entry(manifest: dict, clip_id: str, new_entry: dict) -> None:
    """Replace current state while retaining every earlier attempt as evidence."""
    clips = manifest.setdefault("clips", {})
    previous = clips.get(clip_id)
    entry = dict(new_entry)
    if previous:
        history = list(previous.get("attempt_history", []))
        prior = {k: v for k, v in previous.items() if k != "attempt_history"}
        history.append(prior)
        entry["attempt_history"] = history
    clips[clip_id] = entry


# ── Clip list builder ─────────────────────────────────────────────────────────

def build_clip_list() -> list[dict]:
    """Returns clips in story order with all fields needed for rendering."""
    story = json.loads(STORY_CFG.read_text(encoding="utf-8-sig"))
    audio_map: dict[str, dict] = {}
    for c in json.loads(AUDIO_CFG.read_text(encoding="utf-8-sig")).get("clips", []):
        audio_map[c["id"]] = c

    clips = []
    for sc in story.get("clips", []):
        cid = sc["id"]
        ac = audio_map.get(cid)
        clips.append({
            "id": cid,
            "duration": float(sc.get("duration", 8)),
            "first_frame": sc.get("first_frame", ""),
            "prompt_file": ac["prompt_file"] if ac else None,
            "prompt_inline": None if ac else sc.get("prompt", ""),
            "ref_audios": [r["wav"] for r in ac.get("ref_audios", [])] if ac else [],
            "is_dialogue": ac is not None,
        })
    return clips


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> int:
    LOG.parent.mkdir(parents=True, exist_ok=True)

    if not claim_queue():
        return 3

    clips = build_clip_list()
    total = len(clips)
    emit(f"Single-pass supervisor starting: {total} clips total")

    comfy_pid: int | None = None
    consecutive_failures = 0

    try:
        for idx, clip in enumerate(clips, 1):
            cid = clip["id"]
            kind = "ref2va" if clip["is_dialogue"] else "fl2va"
            manif = load_manifest()
            entry = manif["clips"].get(cid, {})

            # Skip clips already rendered with a valid file
            if entry.get("status") == "valid" and Path(entry.get("comfy_source", "")).exists():
                emit(f"[{idx}/{total}] {cid}: already done — skip")
                continue

            # A raw may be complete even when an older output parser failed to
            # recognize Core SaveVideo's ``images`` result key. Recover it only
            # after native ffprobe checks; this is mechanical validity, not
            # visual acceptance.
            recovered_path, probe = find_existing_valid_render(cid, clip["duration"])
            if recovered_path:
                record_clip_entry(manif, cid, {
                    "status": "valid",
                    "kind": kind,
                    "comfy_source": str(recovered_path),
                    "prompt_id": entry.get("prompt_id"),
                    "seed": entry.get("seed"),
                    "recovered_at": datetime.now().isoformat(timespec="seconds"),
                    "recovery_reason": "existing raw passed ffprobe after SaveVideo parser fix",
                    "mechanical_probe": probe,
                })
                save_manifest(manif)
                emit(f"[{idx}/{total}] {cid}: RECOVERED existing raw → {recovered_path}")
                consecutive_failures = 0
                continue

            # Prepare source materials
            try:
                first_frame_file = ensure_frame_in_input(clip["first_frame"])
            except FileNotFoundError as e:
                emit(f"[{idx}/{total}] {cid}: MISSING frame — {e}; skip")
                record_clip_entry(manif, cid, {"status": "error", "error": str(e)})
                save_manifest(manif)
                consecutive_failures += 1
                continue

            audio_files: list[str] = []
            if clip["is_dialogue"]:
                if not clip["ref_audios"]:
                    error = "Dialogue clip has no approved voice reference; deferred until VOX pass"
                    emit(f"[{idx}/{total}] {cid}: MISSING audio ref — {error}; skip")
                    record_clip_entry(manif, cid, {"status": "error", "error": error})
                    save_manifest(manif)
                    consecutive_failures += 1
                    continue
                try:
                    for wav_rel in clip["ref_audios"]:
                        audio_files.append(ensure_audio_in_input(wav_rel))
                except FileNotFoundError as e:
                    emit(f"[{idx}/{total}] {cid}: MISSING audio ref — {e}; skip")
                    record_clip_entry(manif, cid, {"status": "error", "error": str(e)})
                    save_manifest(manif)
                    consecutive_failures += 1
                    continue

            # Load prompt
            if clip["prompt_file"]:
                pfile = PROJECT / clip["prompt_file"]
                prompt_text = pfile.read_text(encoding="utf-8").strip()
            else:
                prompt_text = (clip["prompt_inline"] or "").strip()

            seed = random.randint(0, 2 ** 53)
            out_prefix = f"story/SP_{cid}/{cid}"
            frames = frame_count(clip["duration"])
            emit(f"[{idx}/{total}] {cid}: {kind}, {clip['duration']}s, {frames} frames, seed={seed}")

            # Build workflow
            if clip["is_dialogue"]:
                wf = build_ref2va_workflow(
                    cid, clip["duration"], first_frame_file,
                    audio_files, prompt_text, seed, out_prefix)
            else:
                wf = build_fl2va_workflow(
                    cid, clip["duration"], first_frame_file,
                    prompt_text, seed, out_prefix)

            # Clean backend per clip
            if api_ready():
                stop_comfy(comfy_pid)
            comfy_pid = start_comfy()

            try:
                prompt_id = submit_workflow(wf)
                emit(f"  {cid}: queued prompt_id={prompt_id}")
                outputs = wait_for_completion(prompt_id, cid)
                video_path = find_video_output(outputs)

                if video_path:
                    emit(f"  {cid}: DONE → {video_path}")
                    manif = load_manifest()
                    record_clip_entry(manif, cid, {
                        "status": "valid",
                        "kind": kind,
                        "comfy_source": video_path,
                        "prompt_id": prompt_id,
                        "seed": seed,
                        "rendered_at": datetime.now().isoformat(timespec="seconds"),
                    })
                    save_manifest(manif)
                    consecutive_failures = 0
                else:
                    emit(f"  {cid}: FAIL — no video in outputs {list(outputs.keys())}")
                    manif = load_manifest()
                    record_clip_entry(manif, cid, {
                        "status": "failed",
                        "prompt_id": prompt_id,
                        "outputs": str(outputs)[:200],
                    })
                    save_manifest(manif)
                    consecutive_failures += 1

            except Exception as e:
                emit(f"  {cid}: ERROR — {e}")
                manif = load_manifest()
                record_clip_entry(manif, cid, {"status": "error", "error": str(e)})
                save_manifest(manif)
                consecutive_failures += 1

            if api_ready():
                stop_comfy(comfy_pid)
                comfy_pid = None

            if consecutive_failures >= 10:
                emit("Ten consecutive failures; pausing for diagnosis")
                return 2

            # Progress report
            manif = load_manifest()
            done = sum(1 for v in manif["clips"].values() if v.get("status") == "valid")
            emit(f"Progress: {done}/{total} valid | next clip after {cid}")

    finally:
        if api_ready():
            stop_comfy(comfy_pid)
        release_queue()

    manif = load_manifest()
    done = sum(1 for v in manif["clips"].values() if v.get("status") == "valid")
    emit(f"Supervisor done: {done}/{total} clips valid")
    return 0 if done == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
