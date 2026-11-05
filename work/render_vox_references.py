#!/usr/bin/env python3
"""Render and measure the seven purpose-built Equal Shares VOX references.

These clips are voice-source material only. They never enter story_config.json,
manifest.json, visual_audit.json, or the completion audit. Every raw attempt is
preserved in ComfyUI-Shared/output/story/VOX_*.

This program is deliberately queue-aware. It exits without touching the GPU if
another live process owns outputs/equal_shares/runtime/render_queue_owner.json.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import thermal_guard


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
SPECS_PATH = PROJECT / "voice_reference_vox_specs.json"
PROMPT_DIR = PROJECT / "prompts_vox"
MANIFEST = PROJECT / "vox_reference_manifest.json"
LOG = PROJECT / "runtime" / "vox_reference_supervisor.log"
OWNER_LOCK = PROJECT / "runtime" / "render_queue_owner.json"

COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
COMFY_PYTHON = COMFY_ROOT / ".venv" / "Scripts" / "python.exe"
MODEL_PATHS = PROJECT / "runtime" / "minimax_model_paths.yaml"
COMFY_RUNTIME = PROJECT / "runtime" / "codex_comfy_runtime"
SHARED_INPUT = COMFY_RUNTIME / "input"
SHARED_OUTPUT = COMFY_RUNTIME / "output"
COMFY_USER = COMFY_RUNTIME / "user"
COMFY_TEMP = COMFY_RUNTIME / "temp"
API = "http://127.0.0.1:8188"

UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
CLIP_NAME = "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
VAE_VIDEO = "minimax_h3_video_vae_fp16.safetensors"
VAE_AUDIO = "minimax_h3_audio_vae_fp32.safetensors"

MIN_SPEECH_SECONDS = 6.0
MIN_SPEECH_DENSITY = 0.70
MAX_ATTEMPTS = 5


def emit(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {message}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def process_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"if (Get-Process -Id {pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
        capture_output=True,
    )
    return result.returncode == 0


def claim_queue() -> bool:
    if OWNER_LOCK.exists():
        try:
            owner = json.loads(OWNER_LOCK.read_text(encoding="utf-8-sig"))
            owner_pid = int(owner.get("pid", 0))
        except Exception:
            owner_pid = 0
        if owner_pid != os.getpid() and process_exists(owner_pid):
            emit(f"Queue is active: pid={owner_pid}, purpose={owner.get('purpose', 'unknown')}; no action taken")
            return False
    OWNER_LOCK.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "render reauthorized 0.2 MP VOX identity masters for H3 Omni-Reference",
    }, indent=2), encoding="utf-8")
    return True


def release_queue() -> None:
    OWNER_LOCK.write_text(json.dumps({
        "pid": 0,
        "released_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "released after VOX reference rendering",
    }, indent=2), encoding="utf-8")


def api_ready() -> bool:
    try:
        with urllib.request.urlopen(f"{API}/system_stats", timeout=5):
            return True
    except Exception:
        return False


def start_comfy() -> int:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for directory in (SHARED_INPUT, SHARED_OUTPUT, COMFY_USER, COMFY_TEMP):
        directory.mkdir(parents=True, exist_ok=True)
    stdout = (PROJECT / "runtime" / f"comfy_vox_{stamp}.stdout.log").open("ab")
    stderr = (PROJECT / "runtime" / f"comfy_vox_{stamp}.stderr.log").open("ab")
    args = [
        str(COMFY_PYTHON), "main.py",
        "--listen", "127.0.0.1", "--port", "8188",
        "--disable-auto-launch",
        "--extra-model-paths-config", str(MODEL_PATHS),
        "--output-directory", str(SHARED_OUTPUT),
        "--input-directory", str(SHARED_INPUT),
        "--user-directory", str(COMFY_USER),
        "--temp-directory", str(COMFY_TEMP),
        "--disable-all-custom-nodes", "--use-sage-attention",
    ]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.Popen(
        args, cwd=COMFY_ROOT, stdout=stdout, stderr=stderr,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), env=env,
    )
    emit(f"Started clean ComfyUI backend pid={proc.pid}")
    try:
        for _ in range(90):
            if api_ready():
                emit("ComfyUI API ready")
                return proc.pid
            if proc.poll() is not None:
                raise RuntimeError(f"ComfyUI exited during startup rc={proc.returncode}")
            time.sleep(5)
        raise TimeoutError("ComfyUI did not become ready within 450 seconds")
    except BaseException:
        # The caller cannot own a PID that start_comfy has not returned. Clean
        # up this exact child here so failed startup never leaves an orphaned
        # backend on port 8188.
        if proc.poll() is None:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Stop-Process -Id {proc.pid} -Force -ErrorAction SilentlyContinue"],
                capture_output=True,
            )
        raise


def stop_comfy(pid: int | None) -> None:
    if not pid:
        emit("Refusing to stop an unowned ComfyUI backend")
        return
    try:
        urllib.request.urlopen(
            urllib.request.Request(
                f"{API}/interrupt", data=b"{}",
                headers={"Content-Type": "application/json"}, method="POST"),
            timeout=5,
        ).read()
    except Exception:
        pass
    time.sleep(2)
    if pid:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Stop-Process -Id {pid} -Force -ErrorAction SilentlyContinue"],
            capture_output=True,
        )
    for _ in range(20):
        if not api_ready():
            emit("ComfyUI stopped; GPU state cleared")
            return
        time.sleep(1)
    emit("WARNING: backend did not stop within 20 seconds")


def ensure_frame(frame_rel: str) -> str:
    SHARED_INPUT.mkdir(parents=True, exist_ok=True)
    encoded = frame_rel.replace("/", "__").replace("\\", "__")
    png = SHARED_INPUT / encoded
    jpg = SHARED_INPUT / encoded.replace(".png", ".jpg")
    if png.exists():
        return encoded
    if jpg.exists():
        return jpg.name
    src = PROJECT / frame_rel
    if not src.exists():
        raise FileNotFoundError(f"VOX anchor missing: {src}")
    shutil.copy2(src, png)
    return encoded


def build_workflow(spec: dict, frame_file: str, prompt: str, seed: int, attempt: int) -> dict:
    out_prefix = f"story/{spec['id']}/attempt_{attempt}"
    return {
        "115": {"class_type": "ResolutionSelector", "inputs": {
            "aspect_ratio": "16:9 (Widescreen)", "megapixels": 0.2, "multiple": 32}},
        "119": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
        "120": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
        "127": {"class_type": "UNETLoader", "inputs": {
            "unet_name": UNET, "weight_dtype": "default"}},
        "128": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": CLIP_NAME, "type": "minimax", "device": "default"}},
        "132": {"class_type": "PrimitiveFloat", "inputs": {"value": 15.0}},
        "131": {"class_type": "ComfyMathExpression", "inputs": {
            "expression": "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17",
            "values.a": ["132", 0]}},
        "137": {"class_type": "LoadImage", "inputs": {"image": frame_file}},
        "138": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": prompt}},
        "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "124": {"class_type": "BasicScheduler", "inputs": {
            "scheduler": "simple", "steps": 20, "denoise": 1.0, "model": ["127", 0]}},
        "136": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
            "prompt": ["138", 0], "width": ["115", 0], "height": ["115", 1],
            "length": ["131", 1], "clip": ["128", 0], "vae": ["119", 0],
            "first_frame": ["137", 0]}},
        "126": {"class_type": "BasicGuider", "inputs": {
            "model": ["127", 0], "conditioning": ["136", 0]}},
        "125": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["129", 0], "guider": ["126", 0], "sampler": ["123", 0],
            "sigmas": ["124", 0], "latent_image": ["136", 1]}},
        "122": {"class_type": "VAEDecode", "inputs": {
            "samples": ["125", 0], "vae": ["119", 0]}},
        "121": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["125", 0], "vae": ["120", 0]}},
        "130": {"class_type": "CreateVideo", "inputs": {
            "fps": 24.0, "bit_depth": 8, "images": ["122", 0], "audio": ["121", 0]}},
        "92": {"class_type": "SaveVideo", "inputs": {
            "filename_prefix": out_prefix, "format": "auto", "codec": "auto",
            "video": ["130", 0]}},
    }


def submit(workflow: dict) -> str:
    request = urllib.request.Request(
        f"{API}/prompt", data=json.dumps({"prompt": workflow}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read())
    if "error" in result:
        raise RuntimeError(str(result))
    return result["prompt_id"]


def wait_for_completion(prompt_id: str, clip_id: str, timeout_seconds: int = 7200) -> dict:
    started = time.time()
    last_report = started
    while time.time() - started < timeout_seconds:
        time.sleep(15)
        thermal_guard.check_running_ceiling(emit, clip_id)
        try:
            with urllib.request.urlopen(f"{API}/history/{prompt_id}", timeout=10) as response:
                history = json.loads(response.read())
            if history:
                return history.get(prompt_id, {}).get("outputs", {})
        except Exception:
            pass
        now = time.time()
        if now - last_report >= 60:
            emit(f"{clip_id}: {(now-started)/60:.1f} min elapsed")
            last_report = now
    raise TimeoutError(f"{clip_id}: timed out after {timeout_seconds//60} minutes")


def find_video(outputs: dict) -> Path | None:
    for node in outputs.values():
        if not isinstance(node, dict):
            continue
        for key in ("video", "videos", "gifs", "images"):
            items = node.get(key, [])
            if isinstance(items, dict):
                items = [items]
            for item in items:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename", "")
                path = SHARED_OUTPUT / item.get("subfolder", "") / filename
                if path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi"} and path.is_file():
                    return path
    return None


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"created": datetime.now().isoformat(timespec="seconds"), "clips": {}}


def save_manifest(data: dict) -> None:
    temp = MANIFEST.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temp, MANIFEST)


def extract_audio(video: Path, clip_id: str, attempt: int) -> Path:
    out = video.with_name(f"{clip_id}_attempt_{attempt}_audio.wav")
    if out.exists():
        return out
    result = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-n", "-i", str(video),
        "-vn", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(out),
    ], capture_output=True, text=True)
    if result.returncode or not out.exists():
        raise RuntimeError(f"audio extraction failed: {result.stderr.strip()[:200]}")
    return out


def measure(audio: Path) -> dict:
    result = subprocess.run(
        [str(COMFY_PYTHON), str(ROOT / "work" / "speech_density.py"), str(audio), "--json"],
        capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f"speech-density failed: {result.stderr.strip()[:200]}")
    rows = json.loads(result.stdout)
    if not rows:
        raise RuntimeError("speech-density returned no measurement")
    row = rows[0]
    row["metric_pass"] = bool(
        row.get("longest_run", 0) >= MIN_SPEECH_SECONDS
        and row.get("speech_fraction", 0) >= MIN_SPEECH_DENSITY)
    return row


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", help="render only this VOX id; repeatable")
    parser.add_argument("--prompt-dir", help="versioned VOX prompt override directory")
    parser.add_argument("--prompt-profile", default="vox_master_v1")
    parser.add_argument("--check", action="store_true", help="show selected VOX work without rendering")
    args = parser.parse_args()
    prompt_dir = Path(args.prompt_dir).resolve() if args.prompt_dir else PROMPT_DIR
    specs = json.loads(SPECS_PATH.read_text(encoding="utf-8"))["clips"]
    if args.only:
        wanted = set(args.only)
        specs = [spec for spec in specs if spec["id"] in wanted]
        missing = wanted - {spec["id"] for spec in specs}
        if missing:
            raise SystemExit("unknown VOX ids: " + ", ".join(sorted(missing)))
    if args.check:
        print(json.dumps({
            "mode": "user_reauthorized_omni_voice_master_bootstrap",
            "megapixels": 0.2,
            "steps": 20,
            "turbo": False,
            "prompt_dir": str(prompt_dir),
            "prompt_profile": args.prompt_profile,
            "clips": [spec["id"] for spec in specs],
        }, indent=2))
        return 0
    selected_ids = {spec["id"] for spec in specs}
    if not claim_queue():
        return 3
    backend_pid: int | None = None
    try:
        for index, spec in enumerate(specs, 1):
            clip_id = spec["id"]
            manifest = load_manifest()
            existing = manifest["clips"].get(clip_id, {})
            if existing.get("status") == "metric_pass" and Path(existing.get("video", "")).exists():
                emit(f"[{index}/{len(specs)}] {clip_id}: measured pass already exists; skip")
                continue

            prompt_path = prompt_dir / f"{clip_id}.txt"
            if not prompt_path.is_file():
                raise FileNotFoundError(f"VOX prompt missing: {prompt_path}")
            prompt = prompt_path.read_text(encoding="utf-8").strip()
            frame_file = ensure_frame(spec["first_frame"])
            prior_attempts = existing.get("attempts", [])
            first_attempt = 1 + max([int(a.get("attempt", 0)) for a in prior_attempts] or [0])

            passed = False
            for attempt in range(first_attempt, first_attempt + MAX_ATTEMPTS):
                seed = random.randint(0, 2**53)
                emit(f"[{index}/{len(specs)}] {clip_id}: attempt {attempt}, 0.2 MP, 15 s, 362 frames, seed={seed}")
                if api_ready() and backend_pid is None:
                    raise RuntimeError(
                        "port 8188 is occupied by an unowned ComfyUI backend; "
                        "refusing to stop it or add a second GPU workload"
                    )
                thermal_guard.wait_before_render(emit)
                backend_pid = start_comfy()
                record = {"attempt": attempt, "seed": seed,
                          "started": datetime.now().isoformat(timespec="seconds"),
                          "prompt_file": str(prompt_path),
                          "prompt_profile": args.prompt_profile}
                try:
                    prompt_id = submit(build_workflow(spec, frame_file, prompt, seed, attempt))
                    record["prompt_id"] = prompt_id
                    outputs = wait_for_completion(prompt_id, clip_id)
                    video = find_video(outputs)
                    if not video:
                        raise RuntimeError("no saved video returned")
                    audio = extract_audio(video, clip_id, attempt)
                    metrics = measure(audio)
                    record.update({"video": str(video), "audio": str(audio), "metrics": metrics})
                    record["status"] = "metric_pass" if metrics["metric_pass"] else "metric_fail"
                    emit(
                        f"{clip_id}: {metrics['longest_run']:.1f}s longest speech, "
                        f"{metrics['speech_fraction']:.0%} density — {record['status']}")
                except Exception as error:
                    record.update({"status": "error", "error": str(error)})
                    emit(f"{clip_id}: attempt {attempt} error — {error}")
                finally:
                    if backend_pid is not None and api_ready():
                        stop_comfy(backend_pid)
                    backend_pid = None
                    thermal_guard.wait_after_render(emit)

                manifest = load_manifest()
                entry = manifest["clips"].setdefault(clip_id, {"character": spec["character"], "attempts": []})
                entry.setdefault("attempts", []).append(record)
                if record["status"] == "metric_pass":
                    entry.update({
                        "status": "metric_pass", "video": record["video"],
                        "audio": record["audio"], "accepted_attempt": attempt,
                        "metrics": record["metrics"],
                        "audio_only_review": "pending ear check for one voice and no invented music",
                    })
                    passed = True
                else:
                    entry["status"] = record["status"]
                save_manifest(manifest)
                if passed:
                    break

            if not passed:
                emit(f"{clip_id}: no metric pass after {MAX_ATTEMPTS} preserved attempts")

        manifest = load_manifest()
        selected_good = sum(
            1 for clip_id in selected_ids
            if manifest["clips"].get(clip_id, {}).get("status") == "metric_pass"
        )
        emit(f"Selected VOX render stage complete: {selected_good}/{len(selected_ids)} measured passes")
        return 0 if selected_good == len(selected_ids) else 1
    finally:
        if backend_pid is not None and api_ready():
            stop_comfy(backend_pid)
        release_queue()


if __name__ == "__main__":
    raise SystemExit(main())
