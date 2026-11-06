#!/usr/bin/env python3
"""Live first-last-frame hardware QA against local ComfyUI (RTX 5080 16 GB).

Does not start ComfyUI. Pings :8188, routes start/end stills through
PipelineOrchestrator (offline temporal-physics fallback), polls nvidia-smi
every 2s, and POSTs /interrupt + /free if used VRAM exceeds 15500 MiB.

Not a simulator: if :8188 is down this process exits 2.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

from local_agent.dispatcher import (  # noqa: E402
    DEFAULT_COMFY_URL,
    PipelineOrchestrator,
)
from local_agent import comfy_api  # noqa: E402
from local_agent import temporal_physics as tp  # noqa: E402

VRAM_LIMIT_MIB = 15500
POLL_S = 2.0
JOB_TIMEOUT_S = 3600.0  # was 600; FLUX+MiniMax 192f exceeds 10min
VIDEO_TIMEOUT_S = 1800.0
TRACE_DIR = ROOT / "logs" / "run_traces"
EXISTING_START = ROOT / "local_agent" / "runtime" / "dspy_opt" / "flf_start_00001_.png"
EXISTING_END = ROOT / "local_agent" / "runtime" / "dspy_opt" / "flf_end_00001_.png"
COMFY_INPUT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\input")
# MiniMax H3 fl2va (32B CLIP) OOMed this 16 GB card. Use Wan 2.2 FLF + GGUF
# Q4 so weights stream; native WanFirstLastFrameToVideo takes start+end images.
UNET_GGUF_HIGH = "wan2.2_i2v_high_noise_14B_Q4_K_M.gguf"
UNET_GGUF_LOW = "wan2.2_i2v_low_noise_14B_Q4_K_M.gguf"
UNET_GGUF = UNET_GGUF_HIGH  # back-compat for logs / callers
# Q6 GGUF CLIP dequant of token_embd crashed Comfy after SDXL. Use fp8 CLIP.
CLIP_WAN_FP8 = "umt5_xxl_fp8_e4m3fn_scaled.safetensors"
VAE_WAN = "wan_2.1_vae.safetensors"
VIDEO_WIDTH = 512
VIDEO_HEIGHT = 288
VIDEO_LENGTH = 17
VIDEO_STEPS = 4
TILE_UNET = "wan2.1_t2v_1.3B_fp16.safetensors"
TILE_CONTROL_NAME = "wan2.1_tile_control.safetensors"
TILE_WIDTH = 1280
TILE_HEIGHT = 720
TILE_DENOISE = 0.35
TILE_STEPS = 4
TILE_STRENGTH = 0.65

START_PROMPT = "First-person POV VHS camcorder looking down an empty yellow hallway."
END_PROMPT = "First-person POV VHS camcorder staring at a dead end wall."
MOTION_PROMPT = (
    "[First-person POV, shaky tracking shot] Walking down the hall until hitting the wall."
)


class VramWatch(threading.Thread):
    def __init__(self, comfy_url: str):
        super().__init__(daemon=True)
        self.comfy_url = comfy_url
        self.phase = "idle"
        self.peaks: dict[str, int] = {}
        self.samples: list[dict] = []
        self.tripped = False
        self._halt = threading.Event()

    def set_phase(self, name: str) -> None:
        self.phase = name
        self.peaks.setdefault(name, 0)

    def request_stop(self) -> None:
        self._halt.set()

    def read_used(self) -> int | None:
        try:
            raw = subprocess.check_output(
                [
                    "nvidia-smi",
                    "--query-gpu=memory.used",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
                timeout=3,
            )
            return int(float(raw.strip().splitlines()[0].strip()))
        except Exception:
            return None

    def _trip(self, used: int) -> None:
        self.tripped = True
        print(f"VRAM TRIP {used} MiB > {VRAM_LIMIT_MIB} MiB â€” POST /interrupt and /free")
        try:
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{self.comfy_url}/interrupt",
                    data=b"{}",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                ),
                timeout=5,
            ).read()
        except Exception as exc:
            print(f"/interrupt failed: {exc}")
        try:
            comfy_api.free_vram(self.comfy_url)
        except Exception as exc:
            print(f"/free failed: {exc}")

    def run(self) -> None:
        while not self._halt.is_set():
            used = self.read_used()
            if used is not None:
                peak = max(self.peaks.get(self.phase, 0), used)
                self.peaks[self.phase] = peak
                self.samples.append({
                    "t": time.time(),
                    "phase": self.phase,
                    "used_mib": used,
                })
                print(f"vram phase={self.phase} used={used} MiB peak={peak} MiB")
                if used > VRAM_LIMIT_MIB and not self.tripped:
                    self._trip(used)
            self._halt.wait(POLL_S)


def _log_fallback(label: str, prompt: str) -> str:
    lm = tp._dspy_lm_available()
    expanded = tp.runtime_inject_temporal_physics(prompt, style="backrooms")
    if lm:
        print(f"[{label}] DSPy LM is configured â€” compiled injector may run")
    else:
        print(
            f"[{label}] no local DSPy LM â€” runtime_inject_temporal_physics "
            "fell back to deterministic inject_temporal_physics"
        )
    print(f"[{label}] injected: {expanded[:240]}")
    return expanded


def _submit_still(orch: PipelineOrchestrator, prompt: str, stem: str) -> Path:
    graph = orch.build_and_dispatch_payload(prompt, "16:9", "sdxl", "backrooms")
    save = graph.get("7") or {}
    if isinstance(save.get("inputs"), dict):
        save["inputs"]["filename_prefix"] = comfy_api.save_prefix(stem)
        if save.get("class_type") == "SaveImageWebsocket":
            save["class_type"] = "SaveImage"
            save["inputs"].setdefault("filename_prefix", comfy_api.save_prefix(stem))
    queued = orch.submit_prompt(graph)
    prompt_id = queued["prompt_id"]
    print(f"queued still {stem} prompt_id={prompt_id}")
    tracked = orch.track_prompt_id(prompt_id, timeout_s=JOB_TIMEOUT_S)
    if tracked.get("state") != "complete":
        raise SystemExit(f"still {stem} failed: {tracked}")
    path = comfy_api.wait_for_image(prompt_id, url=orch.comfy_url, timeout_s=30)
    print(f"still wrote {path}")
    return path


def _upload_png(path: Path, url: str) -> str:
    """Put a PNG into ComfyUI's LoadImage list. Copy + /upload/image."""
    COMFY_INPUT.mkdir(parents=True, exist_ok=True)
    dest = COMFY_INPUT / path.name
    shutil.copy2(path, dest)
    boundary = uuid.uuid4().hex
    filename = path.name
    data = path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + data + (
        f"\r\n--{boundary}\r\n"
        'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"true\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/upload/image",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return str(result.get("name") or filename)
    except Exception as exc:
        print(f"upload/image failed ({exc}); using copied {dest.name}")
        return filename


def build_fl2va_graph(start_name: str, end_name: str, prompt: str, prefix: str) -> dict:
    """Wan 2.2 first-last-frame API graph (GGUF Q4) for 16 GB.

    MiniMaxH3ImageToVideo + 32B CLIP killed Rockernow (process exit, VRAM 116).
    Native ``WanFirstLastFrameToVideo`` maps start_image / end_image / text.

    Wan 2.2 I2V is a high→low MoE pair: KSamplerAdvanced hands the latent from
    the high-noise expert to the low-noise expert mid-schedule without re-noising.
    """
    steps = int(VIDEO_STEPS)
    mid = max(1, steps // 2)
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET_GGUF_HIGH}},
        "1b": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": UNET_GGUF_LOW}},
        "2": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": CLIP_WAN_FP8, "type": "wan", "device": "cpu",
        }},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_WAN}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {
            "text": prompt, "clip": ["2", 0],
        }},
        "5": {"class_type": "CLIPTextEncode", "inputs": {
            "text": "static shot, morphing, still image, text, watermark",
            "clip": ["2", 0],
        }},
        "6": {"class_type": "LoadImage", "inputs": {"image": start_name}},
        "7": {"class_type": "LoadImage", "inputs": {"image": end_name}},
        "8": {"class_type": "WanFirstLastFrameToVideo", "inputs": {
            "positive": ["4", 0],
            "negative": ["5", 0],
            "vae": ["3", 0],
            "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT,
            "length": VIDEO_LENGTH,
            "batch_size": 1,
            "start_image": ["6", 0],
            "end_image": ["7", 0],
        }},
        "9": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["1", 0],
            "positive": ["8", 0],
            "negative": ["8", 1],
            "latent_image": ["8", 2],
            "add_noise": "enable",
            "noise_seed": 42,
            "steps": steps,
            "cfg": 4.0,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "start_at_step": 0,
            "end_at_step": mid,
            "return_with_leftover_noise": "enable",
        }},
        "9b": {"class_type": "KSamplerAdvanced", "inputs": {
            "model": ["1b", 0],
            "positive": ["8", 0],
            "negative": ["8", 1],
            "latent_image": ["9", 0],
            "add_noise": "disable",
            "noise_seed": 42,
            "steps": steps,
            "cfg": 4.0,
            "sampler_name": "uni_pc",
            "scheduler": "simple",
            "start_at_step": mid,
            "end_at_step": steps,
            "return_with_leftover_noise": "disable",
        }},
        "10": {"class_type": "VAEDecode", "inputs": {
            "samples": ["9b", 0], "vae": ["3", 0],
        }},
        "11": {"class_type": "VHS_VideoCombine", "inputs": {
            "images": ["10", 0],
            "frame_rate": 8.0,
            "loop_count": 0,
            "filename_prefix": prefix,
            "format": "video/h264-mp4",
            "pingpong": False,
            "save_output": True,
        }},
    }


def build_tile_upscale_graph(video_path: str, prompt: str, prefix: str) -> dict:
    """Native 1.3B tile-control video conditioning and low-denoise KSampler.

    Input resizing prepares conditioning; every saved frame comes from the
    sampler. Based on spacepxl's native InstructPixToPixConditioning graph.
    """
    return {
        "30": {"class_type": "VHS_LoadVideoPath", "inputs": {
            "video": str(video_path), "force_rate": 8,
            "custom_width": TILE_WIDTH, "custom_height": TILE_HEIGHT,
            "frame_load_cap": VIDEO_LENGTH, "skip_first_frames": 0,
            "select_every_nth": 1, "format": "None",
        }},
        "32": {"class_type": "UNETLoader", "inputs": {
            "unet_name": TILE_UNET, "weight_dtype": "default",
        }},
        "32b": {"class_type": "LoraLoaderModelOnly", "inputs": {
            "model": ["32", 0], "lora_name": TILE_CONTROL_NAME,
            "strength_model": TILE_STRENGTH,
        }},
        "32c": {"class_type": "ModelSamplingSD3", "inputs": {
            "model": ["32b", 0], "shift": 8.0,
        }},
        "33": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": CLIP_WAN_FP8, "type": "wan", "device": "default",
        }},
        "34": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_WAN}},
        "36": {"class_type": "CLIPTextEncode", "inputs": {
            "text": f"{prompt} photorealistic VHS grain, analog camcorder grit, damp concrete texture, sickly yellow wallpaper fiber, 1990s home-video grain, no geometry change",
            "clip": ["33", 0],
        }},
        "37": {"class_type": "CLIPTextEncode", "inputs": {
            "text": "morphing, warping, new geometry, extra limbs, text, watermark",
            "clip": ["33", 0],
        }},
        "38": {"class_type": "InstructPixToPixConditioning", "inputs": {
            "positive": ["36", 0], "negative": ["37", 0],
            "vae": ["34", 0], "pixels": ["30", 0],
        }},
        "39": {"class_type": "VAEEncode", "inputs": {
            "pixels": ["30", 0], "vae": ["34", 0],
        }},
        "40": {"class_type": "KSampler", "inputs": {
            "model": ["32c", 0], "positive": ["38", 0], "negative": ["38", 1],
            "latent_image": ["39", 0], "seed": 42, "steps": TILE_STEPS,
            "cfg": 4.0, "sampler_name": "uni_pc", "scheduler": "simple",
            "denoise": TILE_DENOISE,
        }},
        "41": {"class_type": "VAEDecodeTiled", "inputs": {
            "samples": ["40", 0], "vae": ["34", 0], "tile_size": 512,
            "overlap": 64, "temporal_size": 16, "temporal_overlap": 64,
        }},
        "42": {"class_type": "VHS_VideoCombine", "inputs": {
            "images": ["41", 0], "frame_rate": 8.0, "loop_count": 0,
            "filename_prefix": prefix, "format": "video/h264-mp4",
            "pix_fmt": "yuv420p", "crf": 18, "save_metadata": True,
            "pingpong": False, "save_output": True,
        }},
    }


def wait_for_video(prompt_id: str, url: str, timeout_s: float) -> Path:
    deadline = time.monotonic() + timeout_s
    last = {}
    while time.monotonic() < deadline:
        last = comfy_api.parse_history(
            comfy_api._fetch_history(prompt_id, url=url), prompt_id,
        )
        if last.get("state") == "error":
            raise RuntimeError(f"video job failed: {last}")
        if last.get("state") == "complete":
            for item in last.get("outputs") or []:
                name = str(item.get("filename") or "")
                if name.lower().endswith((".mp4", ".webm", ".mkv", ".mov")):
                    return comfy_api.resolve_output_path(item, url=url)
            raise RuntimeError(f"video job completed with no mp4: {last}")
        time.sleep(2)
    raise TimeoutError(f"video job {prompt_id} timed out after {timeout_s:.0f}s ({last})")


def main() -> int:
    orch = PipelineOrchestrator(comfy_url=DEFAULT_COMFY_URL)
    print(f"ComfyUI {orch.comfy_url}")
    if not comfy_api.ping(orch.comfy_url):
        print(
            "ComfyUI is not listening at http://127.0.0.1:8188.\n"
            "Boot the Rockernow backend (RealVisXL + Impact Pack if FaceDetailer "
            "is required), then re-run:\n"
            "  python live_vram_test.py"
        )
        return 2

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    watch = VramWatch(orch.comfy_url)
    watch.start()
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "comfy_url": orch.comfy_url,
        "vram_limit_mib": VRAM_LIMIT_MIB,
        "fallback": not tp._dspy_lm_available(),
        "files": {},
        "peaks_mib": {},
    }
    try:
        _log_fallback("start", START_PROMPT)
        _log_fallback("end", END_PROMPT)
        _log_fallback("motion", MOTION_PROMPT)

        watch.set_phase("image")
        if EXISTING_START.is_file() and EXISTING_END.is_file():
            start_png = EXISTING_START
            end_png = EXISTING_END
            print(f"reusing stills {start_png.name} / {end_png.name}")
        else:
            start_png = _submit_still(orch, START_PROMPT, "flf_start")
            print("unloading image models via /free before end still")
            comfy_api.free_vram(orch.comfy_url)
            time.sleep(2)
            end_png = _submit_still(orch, END_PROMPT, "flf_end")
        report["files"]["start_png"] = str(start_png)
        report["files"]["end_png"] = str(end_png)

        print("unloading still models via /free before WanFirstLastFrameToVideo")
        comfy_api.free_vram(orch.comfy_url)
        time.sleep(3)
        after_free = watch.read_used()
        report["vram_after_image_free_mib"] = after_free
        print(f"vram after /free: {after_free} MiB")

        motion = tp.runtime_inject_temporal_physics(MOTION_PROMPT, style="backrooms")
        start_name = _upload_png(Path(start_png), orch.comfy_url)
        end_name = _upload_png(Path(end_png), orch.comfy_url)
        graph = build_fl2va_graph(
            start_name, end_name, motion, "dspy_opt/flf_video",
        )
        report["video_workflow"] = {
            "node": "WanFirstLastFrameToVideo",
            "unet": UNET_GGUF,
            "clip": CLIP_GGUF,
            "vae": VAE_WAN,
            "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT,
            "length": VIDEO_LENGTH,
            "steps": VIDEO_STEPS,
            "first_frame": start_name,
            "last_frame": end_name,
        }
        print(
            f"queuing WanFirstLastFrameToVideo unet={UNET_GGUF} "
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}x{VIDEO_LENGTH} steps={VIDEO_STEPS}"
        )
        watch.set_phase("video")
        queued = orch.submit_prompt(graph)
        prompt_id = queued["prompt_id"]
        print(f"queued video prompt_id={prompt_id}")
        tracked = orch.track_prompt_id(prompt_id, timeout_s=VIDEO_TIMEOUT_S)
        if tracked.get("state") != "complete":
            raise SystemExit(f"video job failed: {tracked}")
        mp4 = wait_for_video(prompt_id, orch.comfy_url, timeout_s=60)
        report["files"]["mp4"] = str(mp4)
        report["files"]["mp4_bytes"] = mp4.stat().st_size if mp4.is_file() else 0
        print(f"video wrote {mp4} ({report['files']['mp4_bytes']} bytes)")
        comfy_api.free_vram(orch.comfy_url)
    finally:
        watch.request_stop()
        watch.join(timeout=5)

    report["peaks_mib"] = dict(watch.peaks)
    report["tripped"] = watch.tripped
    report["samples"] = watch.samples[-30:]
    out = TRACE_DIR / f"live_vram_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in (
        "fallback", "peaks_mib", "vram_after_image_free_mib", "files", "tripped",
    )}, indent=2))
    print(f"wrote {out}")
    if watch.tripped:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
