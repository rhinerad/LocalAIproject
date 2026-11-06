#!/usr/bin/env python3
"""Bounded live GPU proof: Ref2VA with dotted image+audio Autogrow (native MiniMax).

Uses two distinct on-disk voice WAVs as ALICE/BOB identity refs (not F5/Fish).
Does not claim calibrated timbre similarity â€” proves production graph emission + execute.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import gvd_graph_builder as ggb
from minimax_ref2vid import attach_minimax_native_audio_mux
import native_voice_continuity as nvc
import production_store as ps

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
OUT_JSON = Path(os.environ.get(
    "OUT_JSON",
    str(ROOT / "live_jobs" / "remaining_20260918_111727" / "live_native_voice_report.json"),
))
SHARED_INPUT = Path(os.environ.get("COMFY_INPUT", r"A:\Users\rhine\ComfyUI-Shared\input"))


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
        "32": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "52": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    }


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
        hist = wait(pid)
        st = hist.get("status") or {}
        if st.get("status_str") == "error":
            raise RuntimeError(str(st.get("messages"))[:1500])
        peak = mon.stop()
        return {
            "name": name,
            "ok": True,
            "prompt_id": pid,
            "wall_clock_s": round(time.time() - t0, 2),
            "baseline_mib": base,
            "peak_mib": peak,
            "status": st.get("status_str"),
            "outputs": hist.get("outputs"),
        }
    except Exception as e:
        peak = mon.stop()
        return {"name": name, "ok": False, "error": str(e)[:1500], "wall_clock_s": round(time.time() - t0, 2), "peak_mib": peak}


def ensure_inputs():
    img = "astra_live_continuity/frame_000.png"
    alice = "astra_voice_ALICE.wav"
    bob = "astra_voice_BOB.wav"
    for rel in (img, alice, bob):
        if not (SHARED_INPUT / rel).is_file() and not (SHARED_INPUT / Path(rel).name).is_file():
            # allow flat names
            flat = SHARED_INPUT / Path(rel).name
            if not flat.is_file():
                raise FileNotFoundError(rel)
    return img, alice, bob


def build_dual_char_graph(img, alice_wav, bob_wav, length=39, steps=8):
    """Shorter length/steps for bounded proof while still exercising audio Autogrow."""
    plan = ggb.RefBindingPlan(
        images=[ggb.ImageRef(img, character_id="ALICE", role="identity")],
        audios=[
            ggb.AudioRef(alice_wav, character_id="ALICE", exact_transcript="Hello there friend."),
            ggb.AudioRef(bob_wav, character_id="BOB", exact_transcript="Good to see you."),
        ],
    )
    g = {
        **loaders("minimax_h3_ref2va_pruned_nvfp4.safetensors"),
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": 11}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": ["30", 0], "scheduler": "simple", "steps": steps, "denoise": 1.0},
        },
    }
    g = ggb.apply_ref2va_autogrow(
        g,
        prompt="Two characters converse in a quiet room. Locked medium shot. Subtle motion. No text.",
        plan=plan,
        width=864,
        height=480,
        length=length,
        audio_vae_node=["52", 0],
    )
    ggb.assert_no_bare_ref_images_key(g)
    g["36"] = {"class_type": "BasicGuider", "inputs": {"model": ["30", 0], "conditioning": ["20", 0]}}
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
    g = attach_minimax_native_audio_mux(g)
    g["25"] = {
        "class_type": "SaveVideo",
        "inputs": {
            "video": ["39", 0],
            "filename_prefix": "astra_native_voice/dual_char",
            "format": "mp4",
            "codec": "auto",
        },
    }
    return g, plan


def seed_canonical_store(alice_wav: Path, bob_wav: Path) -> dict:
    db = ps.connect(":memory:")
    nvc.ensure_voice_schema(db)
    # Register pre-existing refs as canonical for job isolation demo (bootstrap already done offline)
    for cid, wav, transcript, shot in (
        ("ALICE", alice_wav, "Hello there friend.", "S_BOOT_A"),
        ("BOB", bob_wav, "Good to see you.", "S_BOOT_B"),
    ):
        nvc.register_candidate(
            db,
            candidate_id=f"cand_{cid}",
            job_id="live_native_voice",
            character_id=cid,
            bootstrap_shot_id=shot,
            bootstrap_attempt_id=f"att_{cid}",
            source_audio_path=wav,
            segment_start_sample=0,
            segment_end_sample=max(1000, wav.stat().st_size),
            reference_audio_path=wav,
            exact_reference_transcript=transcript,
            qa_evidence={"source": "preexisting_ref_wav", "live_smoke": True},
        )
        nvc.promote_canonical(
            db, job_id="live_native_voice", character_id=cid, candidate_id=f"cand_{cid}"
        )
    # dependent shot must see both
    recs = nvc.require_canonical_voices_for_shot(
        db,
        job_id="live_native_voice",
        shot_id="S_DEPENDENT",
        dialogue_lines=[
            {"speaker_id": "ALICE", "text": "Hello there friend."},
            {"speaker_id": "BOB", "text": "Good to see you."},
        ],
        shot_dialogue_index={
            "S_BOOT_A": [{"speaker_id": "ALICE", "text": "Hello there friend."}],
            "S_BOOT_B": [{"speaker_id": "BOB", "text": "Good to see you."}],
            "S_DEPENDENT": [
                {"speaker_id": "ALICE", "text": "Hello there friend."},
                {"speaker_id": "BOB", "text": "Good to see you."},
            ],
        },
    )
    return {"canonical_count": len(recs), "hashes": {r.character_id: r.reference_audio_hash for r in recs}}


def main() -> int:
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")
    img, alice, bob = ensure_inputs()
    alice_path = SHARED_INPUT / alice if (SHARED_INPUT / alice).is_file() else SHARED_INPUT / Path(alice).name
    bob_path = SHARED_INPUT / bob if (SHARED_INPUT / bob).is_file() else SHARED_INPUT / Path(bob).name
    store_info = seed_canonical_store(alice_path, bob_path)
    try:
        nvc.forbid_tts_fallback("fish_audio", native_required=True)
        raise RuntimeError("expected forbid_tts_fallback to raise")
    except nvc.NativeVoiceError:
        pass  # expected fail-closed against Fish/F5
    g, plan = build_dual_char_graph(img, alice, bob)
    # length 49 (~2s) steps 8 for bounded runtime
    print("SUBMIT dual_char_native_voice", flush=True)
    result = run("dual_char_native_voice", g)
    report = {
        "comfyui_version": ver,
        "ok": bool(result.get("ok")),
        "store": store_info,
        "plan": {
            "images": [a.__dict__ for a in plan.images],
            "audios": [a.__dict__ for a in plan.audios],
            "graph_keys": sorted(k for k in g["20"]["inputs"] if k.startswith("ref_")),
        },
        "result": {k: v for k, v in result.items() if k != "outputs"},
        "outputs": result.get("outputs"),
        "notes": (
            "Live smoke of production Autogrow image+dual-audio keys with native MiniMax Ref2VA. "
            "Uses preexisting distinct WAVs as ALICE/BOB identity refs. "
            "Does not claim calibrated speaker-similarity QA."
        ),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("comfyui_version", "ok", "store", "plan")}, indent=2), flush=True)
    print(json.dumps(report["result"], indent=2), flush=True)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())


