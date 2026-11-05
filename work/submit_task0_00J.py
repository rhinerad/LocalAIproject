"""Submit Task 0: 00J at 0.9 MP with ref2va + LoadAudio narrator reference."""
import json
import os
import random
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
OWNER_LOCK = PROJECT / "runtime" / "render_queue_owner.json"

API = "http://127.0.0.1:8188"

# 00J config (verified from audio_pass_config.json)
DURATION    = 12.0
FRAMES      = 294          # max(5,round(12*24))+(5-(max(5,round(12*24))%17))%17 = 288+6 = 294
FIRST_FRAME = "frames__scene_001__boundary_00.jpg"
AUDIO_FILE  = "narrator_h3_voice_ref.wav"
OUT_PREFIX  = "story/TEST_09MP_00J/00J"
SEED        = random.randint(0, 2**53)

PROMPT_PATH = PROJECT / "prompts_audio_pass" / "00J.txt"
PROMPT_TEXT = PROMPT_PATH.read_text(encoding="utf-8").strip()


def claim():
    OWNER_LOCK.parent.mkdir(parents=True, exist_ok=True)
    try:
        owner = json.loads(OWNER_LOCK.read_text(encoding="utf-8-sig"))
        owner_pid = int(owner.get("pid", 0))
    except Exception:
        owner_pid = 0
    if owner_pid != os.getpid():
        import subprocess
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"if (Get-Process -Id {owner_pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}"],
            capture_output=True,
        )
        if result.returncode == 0:
            print(f"Queue owned by live pid={owner_pid}; cannot claim.", flush=True)
            return False
    OWNER_LOCK.write_text(json.dumps({
        "pid": os.getpid(),
        "claimed_at": datetime.now().isoformat(timespec="seconds"),
        "purpose": "Task 0 — 00J at 0.9 MP ref2va test, Claude Code agent",
    }, indent=2), encoding="utf-8")
    print(f"Queue claimed by pid={os.getpid()}", flush=True)
    return True


def build_workflow():
    return {
        # ── Resolution ──────────────────────────────────────────
        "115": {"class_type": "ResolutionSelector", "inputs": {
            "aspect_ratio": "16:9 (Widescreen)",
            "megapixels": 0.9,
            "multiple": 32,
        }},
        # ── Models ──────────────────────────────────────────────
        "119": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "120": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "127": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "minimax_h3_ref2va_pruned_nvfp4.safetensors",
            "weight_dtype": "default",
        }},
        "128": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
            "type": "minimax",
            "device": "default",
        }},
        # ── Duration ────────────────────────────────────────────
        "132": {"class_type": "PrimitiveFloat", "inputs": {"value": DURATION}},
        "131": {"class_type": "ComfyMathExpression", "inputs": {
            "expression": "max(5, round(a * 24)) + (5 - (max(5, round(a * 24)) % 17)) % 17",
            "values.a": ["132", 0],
        }},
        # ── References ──────────────────────────────────────────
        "137": {"class_type": "LoadImage", "inputs": {"image": FIRST_FRAME}},
        "200": {"class_type": "LoadAudio", "inputs": {"audio": AUDIO_FILE}},
        # ── Prompt ──────────────────────────────────────────────
        "138": {"class_type": "PrimitiveStringMultiline", "inputs": {"value": PROMPT_TEXT}},
        # ── Noise / sampler / scheduler ─────────────────────────
        "129": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
        "123": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "124": {"class_type": "BasicScheduler", "inputs": {
            "scheduler": "simple",
            "steps": 20,
            "denoise": 1.0,
            "model": ["127", 0],
        }},
        # ── Conditioning ────────────────────────────────────────
        "136": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
            "prompt": ["138", 0],
            "width": ["115", 0],
            "height": ["115", 1],
            "length": ["131", 1],
            "ref_image_size": "match",
            "clip": ["128", 0],
            "vae": ["119", 0],
            "audio_vae": ["120", 0],
            "ref_images.ref_image_0": ["137", 0],
            "ref_audios.ref_audio_0": ["200", 0],
        }},
        # ── Sampling ────────────────────────────────────────────
        "126": {"class_type": "BasicGuider", "inputs": {
            "model": ["127", 0],
            "conditioning": ["136", 0],
        }},
        "125": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["129", 0],
            "guider": ["126", 0],
            "sampler": ["123", 0],
            "sigmas": ["124", 0],
            "latent_image": ["136", 1],
        }},
        # ── Decode ──────────────────────────────────────────────
        "122": {"class_type": "VAEDecode", "inputs": {
            "samples": ["125", 0],
            "vae": ["119", 0],
        }},
        "121": {"class_type": "VAEDecodeAudio", "inputs": {
            "samples": ["125", 0],
            "vae": ["120", 0],
        }},
        "130": {"class_type": "CreateVideo", "inputs": {
            "fps": 24.0,
            "bit_depth": 8,
            "images": ["122", 0],
            "audio": ["121", 0],
        }},
        # ── Save / preview ──────────────────────────────────────
        "92": {"class_type": "SaveVideo", "inputs": {
            "filename_prefix": OUT_PREFIX,
            "format": "auto",
            "codec": "auto",
            "video": ["130", 0],
        }},
        # Last-frame extractor chain (saves a preview PNG for review)
        "142_1": {"class_type": "GetVideoComponents", "inputs": {"video": ["92", 0]}},
        "142_2": {"class_type": "GetImageSize",       "inputs": {"image": ["142_1", 0]}},
        "142_100": {"class_type": "PrimitiveInt",     "inputs": {"value": -1}},
        "142_99": {"class_type": "ComfyMathExpression", "inputs": {
            "expression": "min(max(int(a if a >= 0 else b + a), 0), b - 1)",
            "values.a": ["142_100", 0],
            "values.b": ["142_2", 2],
        }},
        "142_3": {"class_type": "ImageFromBatch", "inputs": {
            "batch_index": ["142_99", 1],
            "length": 1,
            "image": ["142_1", 0],
        }},
        "143": {"class_type": "SaveImageAdvanced", "inputs": {
            "filename_prefix": "ComfyUI",
            "format": "png",
            "format.bit_depth": "8-bit",
            "format.input_color_space": "sRGB",
            "images": ["142_3", 0],
        }},
        "144": {"class_type": "PreviewImage", "inputs": {"images": ["143", 0]}},
    }


def submit(workflow):
    body = json.dumps({"prompt": workflow}).encode("utf-8")
    req = urllib.request.Request(
        f"{API}/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main():
    if not claim():
        return 1

    wf = build_workflow()
    print(f"Submitting 00J at 0.9 MP, seed={SEED}, frames={FRAMES}", flush=True)
    print(f"  first_frame: {FIRST_FRAME}", flush=True)
    print(f"  audio_ref:   {AUDIO_FILE}", flush=True)
    print(f"  output:      {OUT_PREFIX}", flush=True)

    result = submit(wf)
    if "error" in result:
        print(f"SUBMIT FAILED: {result}", flush=True)
        return 1

    prompt_id = result.get("prompt_id", "?")
    print(f"Queued prompt_id={prompt_id}", flush=True)
    print(f"Monitor at: http://127.0.0.1:8188", flush=True)

    # Poll until done
    import time
    start = time.time()
    while True:
        time.sleep(15)
        try:
            with urllib.request.urlopen(f"{API}/history/{prompt_id}", timeout=10) as r:
                hist = json.loads(r.read())
            if hist:
                elapsed = time.time() - start
                outputs = hist.get(prompt_id, {}).get("outputs", {})
                print(f"DONE in {elapsed/60:.1f} min. outputs={list(outputs.keys())}", flush=True)
                # Find the saved video path
                for node_id, out in outputs.items():
                    if "gifs" in out or "video" in out:
                        files = out.get("gifs") or out.get("video") or []
                        for f in files:
                            print(f"  Video: {f.get('filename','?')} in {f.get('subfolder','?')}", flush=True)
                return 0
        except Exception as e:
            elapsed = time.time() - start
            with urllib.request.urlopen(f"{API}/queue", timeout=5) as r:
                q = json.loads(r.read())
            running = len(q.get("queue_running", []))
            pending = len(q.get("queue_pending", []))
            print(f"  [{elapsed/60:.1f} min] running={running} pending={pending}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
