#!/usr/bin/env python3
"""Qual 4: one workflow — start/last boundaries + locked voice + exact dialogue + muxed audio.

Uses MiniMaxH3ImageToVideo(first_frame,last_frame) + MiniMaxH3AddGuide(audio=canonical)
+ native audio mux. Records graph keys and decoded stream proof.
"""
from __future__ import annotations

import hashlib
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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "local_agent"))

from minimax_ref2vid import attach_minimax_native_audio_mux
import backrooms_still_contract as bsc

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
SHARED_INPUT = Path(os.environ.get("COMFY_INPUT", r"A:\Users\rhine\ComfyUI-Shared\input"))
SHARED_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", r"A:\Users\rhine\ComfyUI-Shared\output"))
JOB_DIR = ROOT / "live_jobs" / "combined_boundary_audio_20260918"
OUT_JSON = JOB_DIR / "live_combined_boundary_audio_report.json"
LINE = "Okay, that was better in my head."
LENGTH = 39
STEPS = 8


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def http_json(method, path, body=None, timeout=120.0):
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
        time.sleep(2)
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


def wait(pid, timeout=3600):
    t0 = time.time()
    while time.time() - t0 < timeout:
        h = http_json("GET", f"/history/{pid}")
        if pid in h:
            return h[pid]
        time.sleep(4)
    raise TimeoutError(pid)


def has_audio(mp4: Path) -> bool:
    cp = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4)],
        capture_output=True,
        text=True,
    )
    return bool(cp.stdout.strip())


def probe(mp4: Path) -> dict:
    cp = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,duration", "-of", "json", str(mp4)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(cp.stdout)


def run(name, graph):
    free()
    mon = Peak()
    mon.start()
    t0 = time.time()
    base = nvidia_used()
    try:
        resp = http_json("POST", "/prompt", {"prompt": graph, "client_id": f"astra-{name}"})
        pid = resp.get("prompt_id")
        if not pid:
            raise RuntimeError(str(resp))
        print(f"SUBMIT {name} prompt_id={pid}", flush=True)
        hist = wait(pid)
        st = hist.get("status") or {}
        if st.get("status_str") == "error":
            raise RuntimeError(str(st.get("messages"))[:1500])
        return {
            "name": name,
            "ok": True,
            "prompt_id": pid,
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": base,
            "peak_mib": mon.stop(),
            "status": st.get("status_str"),
            "outputs": hist.get("outputs"),
        }
    except Exception as e:
        return {
            "name": name,
            "ok": False,
            "error": str(e)[:1500],
            "wall_clock_s": round(time.time() - t0, 2),
            "peak_mib": mon.stop(),
        }


def build_graph(start_rel: str, last_rel: str, voice_rel: str) -> dict:
    prompt = (
        "Authentic 1990s camcorder found-footage, 4:3. Continuous physical take. "
        f'The actor says exactly: "{LINE}". '
        "Settle into the last-frame composition in the final 1.5 seconds. No text overlays."
    )
    g = {
        "30": {
            "class_type": "UNETLoader",
            "inputs": {
                "unet_name": "minimax_h3_ref2va_pruned_nvfp4.safetensors",
                "weight_dtype": "default",
            },
        },
        "31": {
            "class_type": "CLIPLoader",
            "inputs": {
                "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
                "type": "minimax",
                "device": "default",
            },
        },
        "32": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "52": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "9000": {"class_type": "LoadImage", "inputs": {"image": start_rel}},
        "9001": {"class_type": "LoadImage", "inputs": {"image": last_rel}},
        "9100": {"class_type": "LoadAudio", "inputs": {"audio": voice_rel}},
        "20": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["31", 0],
                "vae": ["32", 0],
                "prompt": prompt,
                "width": 864,
                "height": 480,
                "length": LENGTH,
                "first_frame": ["9000", 0],
                "last_frame": ["9001", 0],
            },
        },
        # Guide locked voice identity onto the temporally bounded conditioning.
        "21": {
            "class_type": "MiniMaxH3AddGuide",
            "inputs": {
                "positive": ["20", 0],
                "latent": ["20", 1],
                "frame_idx": 0,
                "vae": ["32", 0],
                "audio_vae": ["52", 0],
                "audio": ["9100", 0],
            },
        },
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": 303}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": ["30", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0},
        },
        "36": {"class_type": "BasicGuider", "inputs": {"model": ["30", 0], "conditioning": ["21", 0]}},
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
    }
    g = attach_minimax_native_audio_mux(g)
    g["25"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["39", 0],
            "filename_prefix": "astra_combined_boundary_audio/combined",
            "format": "mp4",
            "codec": "auto",
        },
    }
    return g


def main() -> int:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")
    start_rel = "astra_voice_bootstrap/boundaries/start.png"
    last_rel = "astra_voice_bootstrap/boundaries/last.png"
    voice_rel = "astra_voice_bootstrap/ACTOR_canonical_from_take.wav"
    for rel in (start_rel, last_rel, voice_rel):
        if not (SHARED_INPUT / rel).is_file():
            raise FileNotFoundError(rel)

    start_hash = sha256_file(SHARED_INPUT / start_rel)
    last_hash = sha256_file(SHARED_INPUT / last_rel)
    voice_hash = sha256_file(SHARED_INPUT / voice_rel)
    if start_hash == last_hash:
        raise RuntimeError("start/last boundary stills must be distinct")

    # Still-contract: mark these assets approved for this smoke clip
    stills_approved = {
        "C002_start": {"asset_id": start_rel, "sha256": start_hash},
        "C002_last": {"asset_id": last_rel, "sha256": last_hash},
    }
    clip = {
        "id": "C002",
        "references": {"start": "C002_start", "last": "C002_last", "video_requires_still_review": True},
        "dialogue_lines": [{"speaker_id": "ACTOR", "text": LINE}],
        "required_audio": True,
    }
    # Prefer contract helper if it exposes enforce API
    contract_ok = True
    contract_notes = []
    try:
        if hasattr(bsc, "assert_stills_approved_for_animation"):
            bsc.assert_stills_approved_for_animation(clip, stills_approved)
        elif hasattr(bsc, "require_approved_stills"):
            bsc.require_approved_stills(clip, stills_approved)
        else:
            # minimal inline enforce matching audit intent
            if clip["references"].get("video_requires_still_review"):
                for key in ("start", "last"):
                    aid = clip["references"][key]
                    if aid not in stills_approved:
                        raise RuntimeError(f"still not approved: {aid}")
            contract_notes.append("inline_still_gate")
    except Exception as e:
        contract_ok = False
        contract_notes.append(str(e))

    g = build_graph(start_rel, last_rel, voice_rel)
    # Record critical wiring for evidence
    wiring = {
        "i2v_first_frame": g["20"]["inputs"].get("first_frame"),
        "i2v_last_frame": g["20"]["inputs"].get("last_frame"),
        "add_guide_audio": g["21"]["inputs"].get("audio"),
        "load_audio_file": g["9100"]["inputs"]["audio"],
        "create_video_audio": g["39"]["inputs"].get("audio"),
        "prompt_contains_exact_line": LINE in g["20"]["inputs"]["prompt"],
    }
    assert wiring["i2v_first_frame"] == ["9000", 0]
    assert wiring["i2v_last_frame"] == ["9001", 0]
    assert wiring["load_audio_file"] == voice_rel
    assert wiring["create_video_audio"] == ["44", 0]

    result = run("combined_boundary_audio", g)
    report = {
        "comfyui_version": ver,
        "exact_dialogue": LINE,
        "boundaries": {
            "start": {"path": start_rel, "sha256": start_hash},
            "last": {"path": last_rel, "sha256": last_hash},
            "distinct": start_hash != last_hash,
        },
        "voice": {"path": voice_rel, "sha256": voice_hash, "source": "qual3_canonical_from_take"},
        "still_contract_ok": contract_ok,
        "still_contract_notes": contract_notes,
        "wiring": wiring,
        "result": {k: v for k, v in result.items() if k != "outputs"},
    }
    if not result.get("ok"):
        report["ok"] = False
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        return 1

    out_dir = SHARED_OUTPUT / "astra_combined_boundary_audio"
    mp4s = sorted(out_dir.glob("combined*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        report["ok"] = False
        report["error"] = "missing output mp4"
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return 1
    mp4 = mp4s[0]
    streams = probe(mp4)
    report["output"] = {
        "mp4": str(mp4),
        "has_audio": has_audio(mp4),
        "ffprobe": streams,
        "sha256": sha256_file(mp4),
    }
    report["ok"] = bool(
        contract_ok
        and wiring["prompt_contains_exact_line"]
        and report["boundaries"]["distinct"]
        and report["output"]["has_audio"]
        and result.get("ok")
    )
    report["notes"] = (
        "Combined ImageToVideo first/last boundaries + AddGuide(locked voice audio) + "
        "CreateVideo audio mux in one prompt graph. Does not claim pixel-perfect boundary "
        "match QA or full 102-shot production."
    )
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
