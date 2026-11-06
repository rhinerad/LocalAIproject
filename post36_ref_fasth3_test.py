#!/usr/bin/env python3
"""Post-0.36 tests: multi-ref (ImageBatch→ref_images + Ref2VA) and FastH3 Dense LoRA."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
OUT = Path(os.environ["OUT_JSON"]) if os.environ.get("OUT_JSON") else Path("post36_report.json")


def http_json(method, path, body=None, timeout=120.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{COMFY}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


def free():
    try:
        http_json("POST", "/free", {"unload_models": True, "free_memory": True})
        time.sleep(2)
    except Exception as e:
        return str(e)
    return "ok"


def nvidia_used():
    try:
        o = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=10,
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


def wait(pid, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = http_json("GET", f"/history/{pid}")
        if pid in h:
            return h[pid]
        time.sleep(4)
    raise TimeoutError(pid)


def loaders(unet: str):
    return {
        "30": {"class_type": "UNETLoader", "inputs": {"unet_name": unet, "weight_dtype": "default"}},
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


def run(name, graph):
    free()
    q = http_json("GET", "/queue")
    if q.get("queue_running") or q.get("queue_pending"):
        return {"name": name, "ok": False, "error": "queue busy"}
    mon = Peak()
    mon.start()
    t0 = time.time()
    base = nvidia_used()
    try:
        resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": f"astra-{name}"})
        pid = resp.get("prompt_id")
        if not pid:
            raise RuntimeError(str(resp))
        hist = wait(pid)
        st = hist.get("status") or {}
        if st.get("status_str") == "error":
            msgs = st.get("messages")
            raise RuntimeError(str(msgs)[:800])
        peak = mon.stop()
        return {
            "name": name,
            "ok": True,
            "prompt_id": pid,
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": base,
            "peak_mib": peak,
            "status": st.get("status_str"),
        }
    except Exception as e:
        peak = mon.stop()
        return {
            "name": name,
            "ok": False,
            "error": str(e)[:1000],
            "wall_clock_s": round(time.time() - t0, 2),
            "peak_mib": peak,
        }


def graph_ref_multi():
    # Ref2VA unet + ImageBatch → ref_images
    model = ["30", 0]
    g = {
        **loaders("minimax_h3_ref2va_pruned_nvfp4.safetensors"),
        "1001": {"class_type": "LoadImage", "inputs": {"image": "astra_live_continuity/frame_000.png"}},
        "1002": {"class_type": "LoadImage", "inputs": {"image": "astra_live_continuity/boundary_last.png"}},
        "1003": {"class_type": "ImageBatch", "inputs": {"image1": ["1001", 0], "image2": ["1002", 0]}},
        "20": {
            "class_type": "MiniMaxH3ReferenceToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": "Same identity and setting as the reference images. Locked medium shot. Subtle natural motion.",
                "width": 864,
                "height": 480,
                "length": 124,
                "ref_image_size": "match",
                "ref_images": ["1003", 0],
            },
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": model, "scheduler": "simple", "steps": 20, "denoise": 1.0},
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
            "inputs": {
                "video": ["39", 0],
                "filename_prefix": "astra_post36/ref_multi",
                "format": "mp4",
                "codec": "auto",
            },
        },
    }
    return g


def graph_fasth3_dense():
    # Base FL2VA + FastH3 Dense LoRA + Kitchen + 6 steps, no Sage
    g = {
        **loaders("minimax_h3_fl2va_pruned_int8_convrot.safetensors"),
        "41": {
            "class_type": "MiniMaxH3TurboLoRA",
            "inputs": {
                "model": ["30", 0],
                "lora_name": "FastH3-Dense-4-step-v1-LoRA-ComfyUI-pruned.safetensors",
                "strength_model": 1.0,
            },
        },
        "42": {
            "class_type": "ModelAttentionBackend",
            "inputs": {"model": ["41", 0], "attention": "comfy kitchen attention"},
        },
        "43": {
            "class_type": "MiniMaxH3SigmaShift",
            "inputs": {"model": ["42", 0]},
        },
        "1001": {"class_type": "LoadImage", "inputs": {"image": "astra_live_continuity/frame_000.png"}},
        "20": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": "Continue from first frame. Locked camera. Subtle motion. No text.",
                "width": 864,
                "height": 480,
                "length": 124,
                "first_frame": ["1001", 0],
            },
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": 77}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": ["43", 0], "scheduler": "simple", "steps": 6, "denoise": 1.0},
        },
        "36": {"class_type": "BasicGuider", "inputs": {"model": ["43", 0], "conditioning": ["20", 0]}},
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
            "inputs": {
                "video": ["39", 0],
                "filename_prefix": "astra_post36/fasth3_dense6",
                "format": "mp4",
                "codec": "auto",
            },
        },
    }
    # Inspect sigma shift required inputs — may need video_shift/audio_shift
    return g


def main():
    # Fix sigma shift inputs from live schema
    try:
        info = http_json("GET", "/object_info/MiniMaxH3SigmaShift")
        req = info["MiniMaxH3SigmaShift"]["input"].get("required", {})
        opt = info["MiniMaxH3SigmaShift"]["input"].get("optional", {})
        print("sigma_required", list(req))
        print("sigma_optional", list(opt))
    except Exception as e:
        print("sigma schema err", e)

    # Turbo LoRA strength key
    try:
        info = http_json("GET", "/object_info/MiniMaxH3TurboLoRA")
        print("turbo_lora_keys", info["MiniMaxH3TurboLoRA"]["input"]["required"].keys())
    except Exception as e:
        print("turbo schema", e)

    results = []
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")

    # Adjust FastH3 graph sigma inputs if needed after schema print — build dynamically
    g_fast = graph_fasth3_dense()
    sigma_info = http_json("GET", "/object_info/MiniMaxH3SigmaShift")["MiniMaxH3SigmaShift"]["input"]
    sin = g_fast["43"]["inputs"]
    for key, spec in {**sigma_info.get("required", {}), **sigma_info.get("optional", {})}.items():
        if key == "model":
            continue
        # defaults
        if isinstance(spec, list) and len(spec) > 1 and isinstance(spec[1], dict) and "default" in spec[1]:
            sin[key] = spec[1]["default"]
    # Preferred shifts from local FastH3 note
    if "video_shift" in sin or "video_shift" in sigma_info.get("required", {}) or "video_shift" in sigma_info.get("optional", {}):
        sin["video_shift"] = 12
    if "audio_shift" in sin or "audio_shift" in sigma_info.get("required", {}) or "audio_shift" in sigma_info.get("optional", {}):
        sin["audio_shift"] = 3

    for name, g in (("ref_multi", graph_ref_multi()), ("fasth3_dense6", g_fast)):
        r = run(name, g)
        results.append(r)
        print(json.dumps(r))
        OUT.write_text(json.dumps({"comfyui_version": ver, "results": results}, indent=2), encoding="utf-8")

    summary = {"comfyui_version": ver, "ok": all(x.get("ok") for x in results), "results": results}
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
