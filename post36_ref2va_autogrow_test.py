#!/usr/bin/env python3
"""Ref2VA via Autogrow slots ref_image_0..N (not IMAGE wired to ref_images)."""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
OUT = Path(os.environ["OUT_JSON"]) if os.environ.get("OUT_JSON") else Path("post36_ref2va_autogrow_report.json")


def http_json(method, path, body=None, timeout=120.0):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"{COMFY}{path}", data=data, method=method,
        headers={"Content-Type": "application/json"} if body is not None else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:2000]
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


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


def graph_ref2va(name_prefix: str, image_slots: list[tuple[str, str]], length=124, steps=20):
    """image_slots: list of (node_id, input_relpath under Comfy input/)."""
    model = ["30", 0]
    g = {
        **loaders("minimax_h3_ref2va_pruned_nvfp4.safetensors"),
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": 42}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": model, "scheduler": "simple", "steps": steps, "denoise": 1.0},
        },
    }
    ref_inputs = {}
    prompt_tags = []
    for i, (nid, rel) in enumerate(image_slots):
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": rel}}
        ref_inputs[f"ref_images.ref_image_{i}"] = [nid, 0]
        prompt_tags.append(f"<Picture {i+1}>")
    tag_str = " and ".join(prompt_tags) if prompt_tags else "the references"
    g["20"] = {
        "class_type": "MiniMaxH3ReferenceToVideo",
        "inputs": {
            "clip": ["31", 0],
            "vae": ["32", 0],
            "prompt": (
                f"Same identity and setting as {tag_str}. "
                "Locked medium shot. Subtle natural motion. No text overlay."
            ),
            "width": 864,
            "height": 480,
            "length": length,
            "ref_image_size": "match",
            **ref_inputs,
        },
    }
    g["36"] = {"class_type": "BasicGuider", "inputs": {"model": model, "conditioning": ["20", 0]}}
    g["37"] = {
        "class_type": "SamplerCustomAdvanced",
        "inputs": {
            "noise": ["33", 0],
            "guider": ["36", 0],
            "sampler": ["34", 0],
            "sigmas": ["35", 0],
            "latent_image": ["20", 1],
        },
    }
    g["38"] = {"class_type": "VAEDecode", "inputs": {"samples": ["37", 0], "vae": ["32", 0]}}
    g["39"] = {"class_type": "CreateVideo", "inputs": {"images": ["38", 0], "fps": 24.0, "bit_depth": 8}}
    g["25"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["39", 0],
            "filename_prefix": f"astra_post36/{name_prefix}",
            "format": "mp4",
            "codec": "auto",
        },
    }
    return g


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
        outs = hist.get("outputs") or {}
        if st.get("status_str") == "error":
            msgs = st.get("messages")
            raise RuntimeError(str(msgs)[:1200])
        peak = mon.stop()
        return {
            "name": name,
            "ok": True,
            "prompt_id": pid,
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": base,
            "peak_mib": peak,
            "status": st.get("status_str"),
            "outputs": outs,
        }
    except Exception as e:
        peak = mon.stop()
        return {
            "name": name,
            "ok": False,
            "error": str(e)[:1500],
            "wall_clock_s": round(time.time() - t0, 2),
            "peak_mib": peak,
        }


def main():
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")
    results = []
    cases = [
        (
            "ref2va_single_autogrow",
            graph_ref2va(
                "ref_single",
                [("1001", "astra_live_continuity/frame_000.png")],
            ),
        ),
        (
            "ref2va_dual_autogrow",
            graph_ref2va(
                "ref_dual",
                [
                    ("1001", "astra_live_continuity/frame_000.png"),
                    ("1002", "astra_live_continuity/boundary_last.png"),
                ],
            ),
        ),
    ]
    for name, g in cases:
        print("SUBMIT", name, flush=True)
        r = run(name, g)
        results.append(r)
        print(json.dumps({k: v for k, v in r.items() if k != "outputs"}), flush=True)
        OUT.write_text(
            json.dumps({"comfyui_version": ver, "ok": all(x.get("ok") for x in results), "results": results}, indent=2),
            encoding="utf-8",
        )
        if not r.get("ok"):
            break
    summary = {
        "comfyui_version": ver,
        "ok": all(x.get("ok") for x in results) and len(results) == len(cases),
        "api_note": "Wire Autogrow as dotted keys ref_images.ref_image_0..N on MiniMaxH3ReferenceToVideo; do not pass IMAGE/ImageBatch to ref_images (Tensor bool ambiguity); bare ref_image_0 is unexpected kwarg.",
        "results": results,
    }
    OUT.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2), flush=True)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


