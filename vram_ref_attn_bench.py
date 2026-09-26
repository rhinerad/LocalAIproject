#!/usr/bin/env python3
"""VRAM envelope + ReferenceToVideo lock + attention compare (live Comfy).

Profiles:
  - 1152x640 / 124 frames / 20 steps (production trial)
  - 1344x768 / 124 frames / 20 steps (high-res trial)
  - ReferenceToVideo multi-ref at 864x480 / 124 (identity lock smoke)
  - Attention: sage auto vs no-sage at 864x480 / 124

Records wall_clock and peak nvidia-smi memory.used via sampler thread.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from copy import deepcopy
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
OUTPUT_DIR = Path(os.environ.get("COMFY_OUTPUT_DIR", r"A:\Users\rhine\ComfyUI-Shared\output"))
INPUT_DIR = Path(os.environ.get("COMFY_INPUT_DIR", r"A:\Users\rhine\ComfyUI-Shared\input"))


def http_json(method: str, path: str, body: dict | None = None, timeout: float = 120.0):
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def free_vram():
    try:
        http_json("POST", "/free", {"unload_models": True, "free_memory": True}, timeout=120.0)
    except Exception as e:
        return str(e)
    time.sleep(2)
    return "ok"


def nvidia_used_mib() -> int | None:
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
        return int(out.strip().splitlines()[0].strip())
    except Exception:
        return None


class PeakMonitor:
    def __init__(self, interval: float = 1.0):
        self.interval = interval
        self.peak = 0
        self.samples = 0
        self._stop = threading.Event()
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()

    def stop(self):
        self._stop.set()
        self._t.join(timeout=5)
        return self.peak

    def _run(self):
        while not self._stop.is_set():
            v = nvidia_used_mib()
            if v is not None:
                self.peak = max(self.peak, v)
                self.samples += 1
            self._stop.wait(self.interval)


def wait_history(prompt_id: str, timeout_s: float) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        hist = http_json("GET", f"/history/{prompt_id}", timeout=30.0)
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(4)
    raise TimeoutError(prompt_id)


def base_loaders(unet="minimax_h3_fl2va_pruned_int8_convrot.safetensors"):
    return {
        "30": {
            "class_type": "UNETLoader",
            "inputs": {"unet_name": unet, "weight_dtype": "default"},
        },
        "31": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                "type": "minimax",
                "device": "default",
            },
        },
        "32": {
            "class_type": "VAELoader",
            "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"},
        },
    }


def i2v_graph(*, image: str, width: int, height: int, length: int, steps: int,
              seed: int, prefix: str, use_sage: bool) -> dict:
    model = ["40", 0] if use_sage else ["30", 0]
    g = {
        **base_loaders(),
        "20": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": "Continue from first frame. Locked camera. Subtle motion. No text.",
                "width": width,
                "height": height,
                "length": length,
                "first_frame": ["1001", 0],
            },
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": model, "scheduler": "simple", "steps": steps, "denoise": 1.0},
        },
        "36": {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["20", 0]}},
        "37": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["33", 0],
                "guider": ["36", 0],
                "sampler": ["34", 0],
                "sigmas": ["35", 0],
                "latent_image": ["20", 1],
            },
        },
        "38": {"class_type": "VAEDecode", "inputs": {"samples": ["37", 0], "vae": ["32", 0]}},
        "39": {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "fps": 24.0, "bit_depth": 8}},
        "25": {
            "class_type": "SaveVideo",
            "inputs": {"video": ["39", 0], "filename_prefix": prefix, "format": "mp4", "codec": "auto"},
        },
        "1001": {"class_type": "LoadImage", "inputs": {"image": image}},
    }
    if use_sage:
        g["40"] = {
            "class_type": "PathchSageAttentionKJ",
            "inputs": {"model": ["30", 0], "sage_attention": "auto", "allow_compile": False},
        }
    return g


def ref_graph(*, refs: list[str], width: int, height: int, length: int, steps: int,
              seed: int, prefix: str, use_sage: bool) -> dict:
    """MiniMaxH3ReferenceToVideo multi-ref smoke (Ref2VA class absent on this install)."""
    model = ["40", 0] if use_sage else ["30", 0]
    g = {
        **base_loaders(),
        "20": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": "Same person and setting as references. Locked medium shot. Subtle motion.",
                "width": width,
                "height": height,
                "length": length,
                "ref_image_size": "match",
            },
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": model, "scheduler": "simple", "steps": steps, "denoise": 1.0},
        },
        "36": {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["20", 0]}},
        "37": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["33", 0],
                "guider": ["36", 0],
                "sampler": ["34", 0],
                "sigmas": ["35", 0],
                "latent_image": ["20", 1],
            },
        },
        "38": {"class_type": "VAEDecode", "inputs": {"samples": ["37", 0], "vae": ["32", 0]}},
        "39": {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "fps": 24.0, "bit_depth": 8}},
        "25": {
            "class_type": "SaveVideo",
            "inputs": {"video": ["39", 0], "filename_prefix": prefix, "format": "mp4", "codec": "auto"},
        },
    }
    # Attach refs as LoadImage + numbered ref_image_N (autogrow API convention)
    for i, name in enumerate(refs, start=1):
        nid = str(1000 + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": name}}
        g["20"]["inputs"][f"ref_image_{i}"] = [nid, 0]
    if use_sage:
        g["40"] = {
            "class_type": "PathchSageAttentionKJ",
            "inputs": {"model": ["30", 0], "sage_attention": "auto", "allow_compile": False},
        }
    return g


def run_one(name: str, graph: dict, timeout: float) -> dict:
    free = free_vram()
    q = http_json("GET", "/queue")
    if (q.get("queue_running") or q.get("queue_pending")):
        return {"name": name, "ok": False, "error": "queue not empty", "free": free}
    mon = PeakMonitor()
    mon.start()
    t0 = time.time()
    baseline = nvidia_used_mib()
    try:
        resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": f"astra-{name}"})
        pid = resp.get("prompt_id")
        if not pid:
            raise RuntimeError(str(resp))
        hist = wait_history(pid, timeout_s=timeout)
        status = hist.get("status") or {}
        if status.get("status_str") == "error":
            raise RuntimeError(str(status))
        wall = round(time.time() - t0, 2)
        peak = mon.stop()
        return {
            "name": name,
            "ok": True,
            "prompt_id": pid,
            "wall_clock_s": wall,
            "baseline_mib": baseline,
            "peak_mib": peak,
            "delta_mib": None if peak is None or baseline is None else peak - baseline,
            "status": status.get("status_str"),
            "free_before": free,
        }
    except Exception as e:
        peak = mon.stop()
        return {
            "name": name,
            "ok": False,
            "error": str(e),
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": baseline,
            "peak_mib": peak,
            "free_before": free,
        }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--image", default="astra_live_continuity/frame_000.png")
    ap.add_argument("--ref2", default="astra_live_continuity/boundary_last.png")
    ap.add_argument("--timeout", type=float, default=3600)
    ap.add_argument("--skip-highres", action="store_true")
    ap.add_argument("--skip-ref", action="store_true")
    ap.add_argument("--skip-attn", action="store_true")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    results = []

    # VRAM envelopes
    if not args.skip_highres:
        for w, h, tag in ((1152, 640, "prod_1152x640"), (1344, 768, "hires_1344x768")):
            g = i2v_graph(
                image=args.image,
                width=w,
                height=h,
                length=124,
                steps=20,
                seed=20260918,
                prefix=f"astra_vram/{tag}",
                use_sage=True,
            )
            r = run_one(tag, g, args.timeout)
            results.append(r)
            out.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
            print(json.dumps(r))

    # Multi-ref
    if not args.skip_ref:
        g = ref_graph(
            refs=[args.image, args.ref2],
            width=864,
            height=480,
            length=124,
            steps=20,
            seed=20260919,
            prefix="astra_vram/ref_multi",
            use_sage=True,
        )
        r = run_one("ref_multi", g, args.timeout)
        results.append(r)
        out.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
        print(json.dumps(r))

    # Attention compare
    if not args.skip_attn:
        for use_sage, tag in ((True, "attn_sage"), (False, "attn_sdpa")):
            g = i2v_graph(
                image=args.image,
                width=864,
                height=480,
                length=124,
                steps=20,
                seed=20260920,
                prefix=f"astra_vram/{tag}",
                use_sage=use_sage,
            )
            r = run_one(tag, g, args.timeout)
            results.append(r)
            out.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")
            print(json.dumps(r))

    summary = {
        "ok": all(r.get("ok") for r in results) if results else False,
        "results": results,
        "comfyui_version": (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version"),
        "fasth3": "skipped_requires_comfy_0_36",
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
