#!/usr/bin/env python3
"""Qualify a 4:3 Flux.1-dev canvas on local Comfy (bounded smoke)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
SHARED_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", r"A:\Users\rhine\ComfyUI-Shared\output"))
JOB_DIR = ROOT / "live_jobs" / "flux_canvas_qualify_20260918"
OUT_JSON = JOB_DIR / "flux_canvas_qualify_report.json"
CKPT = "flux1-dev-fp8.safetensors"
# Comfy "Flux Empty Latent Image" enum label
RESOLUTION = "custom_empty_latent_4x3"
WIDTH, HEIGHT = 1152, 864
STEPS = 8
GUIDANCE = 3.5


def http_json(method, path, body=None, timeout=180.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:2000]}") from e


def free():
    try:
        http_json("POST", "/free", {"unload_models": True, "free_memory": True})
        time.sleep(3)
    except Exception as e:
        return str(e)
    return "ok"


def nvidia_used():
    try:
        o = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True,
            timeout=10,
        )
        return int(o.strip().splitlines()[0])
    except Exception:
        return None


class Peak:
    def __init__(self):
        self.peak = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(5)
        return self.peak

    def _run(self):
        while not self._stop.is_set():
            v = nvidia_used()
            if v is not None:
                self.peak = max(self.peak, v)
            self._stop.wait(1.0)


def wait(pid, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = http_json("GET", f"/history/{pid}")
        if pid in h:
            return h[pid]
        time.sleep(3)
    raise TimeoutError(pid)


def build_graph(prompt: str, seed: int = 42) -> dict:
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": CKPT}},
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "blurry, low quality, watermark, text, logo, deformed hands",
                "clip": ["1", 1],
            },
        },
        "4": {
            "class_type": "FluxGuidance",
            "inputs": {"conditioning": ["2", 0], "guidance": GUIDANCE},
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": WIDTH, "height": HEIGHT, "batch_size": 1},
        },
        "6": {
            "class_type": "ModelSamplingFlux",
            "inputs": {
                "model": ["1", 0],
                "max_shift": 1.15,
                "base_shift": 0.5,
                "width": WIDTH,
                "height": HEIGHT,
            },
        },
        "7": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["6", 0],
                "seed": seed,
                "steps": STEPS,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "positive": ["4", 0],
                "negative": ["3", 0],
                "latent_image": ["5", 0],
                "denoise": 1.0,
            },
        },
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {
            "class_type": "SaveImage",
            "inputs": {"images": ["8", 0], "filename_prefix": "astra_flux_canvas/qual_4x3"},
        },
    }


def find_png(hist_outputs) -> Path | None:
    if isinstance(hist_outputs, dict):
        for node_out in hist_outputs.values():
            if not isinstance(node_out, dict):
                continue
            for item in node_out.get("images") or []:
                if not isinstance(item, dict):
                    continue
                fn = item.get("filename")
                sub = item.get("subfolder") or ""
                if fn:
                    p = SHARED_OUTPUT / sub / fn
                    if p.is_file():
                        return p
    folder = SHARED_OUTPUT / "astra_flux_canvas"
    if folder.is_dir():
        pngs = sorted(folder.glob("qual_4x3*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pngs:
            return pngs[0]
    return None


def probe_png(path: Path) -> dict:
    # prefer ffprobe; fall back to PIL if needed
    try:
        from PIL import Image

        im = Image.open(path)
        w, h = im.size
        return {"width": w, "height": h, "format": im.format, "mode": im.mode}
    except Exception:
        cp = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)],
            capture_output=True,
            text=True,
        )
        data = json.loads(cp.stdout or "{}")
        streams = data.get("streams") or [{}]
        return {"width": streams[0].get("width"), "height": streams[0].get("height")}


def main() -> int:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")
    free()
    prompt = (
        "Authentic 1990s consumer camcorder still, 4:3 composition, ordinary apartment "
        "living room audition space, tripod viewpoint, sharp static reference frame, "
        "mild VHS softness, practical household lighting, no motion blur, no text."
    )
    g = build_graph(prompt)
    mon = Peak()
    mon.start()
    t0 = time.time()
    base = nvidia_used()
    try:
        resp = http_json("POST", "/prompt", {"prompt": g, "client_id": "astra-flux-canvas"})
        pid = resp.get("prompt_id")
        if not pid:
            raise RuntimeError(str(resp))
        print(f"SUBMIT flux_canvas_4x3 prompt_id={pid}", flush=True)
        hist = wait(pid)
        st = hist.get("status") or {}
        if st.get("status_str") == "error":
            raise RuntimeError(str(st.get("messages"))[:2000])
        peak = mon.stop()
        png = find_png(hist.get("outputs"))
        if png is None:
            raise RuntimeError("no output png")
        meta = probe_png(png)
        aspect_ok = (
            meta.get("width") == WIDTH
            and meta.get("height") == HEIGHT
            and abs((meta["width"] / meta["height"]) - (4 / 3)) < 0.01
        )
        report = {
            "ok": bool(aspect_ok),
            "comfyui_version": ver,
            "checkpoint": CKPT,
            "resolution_label": f"EmptyLatentImage {WIDTH}x{HEIGHT}",
            "width": WIDTH,
            "height": HEIGHT,
            "aspect": "4:3",
            "steps": STEPS,
            "guidance": GUIDANCE,
            "prompt_id": pid,
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": base,
            "peak_mib": peak,
            "output_png": str(png),
            "png_meta": meta,
            "aspect_ok": aspect_ok,
            "needs_canvas_qualification": False if aspect_ok else True,
            "notes": "Bounded Flux.1-dev-fp8 smoke at true 4:3 EmptyLatentImage 1152x864 (Comfy Flux preset 1152x896 is 9:7, not 4:3).",
        }
    except Exception as e:
        peak = mon.stop()
        report = {
            "ok": False,
            "comfyui_version": ver,
            "checkpoint": CKPT,
            "resolution_label": f"EmptyLatentImage {WIDTH}x{HEIGHT}",
            "error": str(e)[:2000],
            "peak_mib": peak,
            "wall_clock_s": round(time.time() - t0, 2),
        }
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    # also write machine-readable canvas policy for still runner
    policy = {
        "still_backend": "flux",
        "checkpoint": CKPT,
        "resolution_label": f"EmptyLatentImage {WIDTH}x{HEIGHT}",
        "width": WIDTH,
        "height": HEIGHT,
        "aspect_ratio": "4:3",
        "vertical": False,
        "steps_default": 20,
        "steps_smoke": STEPS,
        "guidance": GUIDANCE,
        "qualified": bool(report.get("ok")),
        "qualify_report": str(OUT_JSON),
    }
    (JOB_DIR / "flux_canvas_policy.json").write_text(json.dumps(policy, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
