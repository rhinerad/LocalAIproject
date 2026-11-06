#!/usr/bin/env python3
"""Qual 3: first MiniMax speaking take -> extract/lock -> dependent line same hash.

Bootstrap shot may use a disposable seed WAV only as Ref2VA conditioner.
The CANONICAL lock is the extracted audio from the first generated take — not the seed.
Dependent shot must LoadAudio the locked file (matching reference_audio_hash).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
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

import gvd_graph_builder as ggb
import native_voice_continuity as nvc
from minimax_ref2vid import attach_minimax_native_audio_mux

COMFY = os.environ.get("COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
SHARED_INPUT = Path(os.environ.get("COMFY_INPUT", r"A:\Users\rhine\ComfyUI-Shared\input"))
SHARED_OUTPUT = Path(os.environ.get("COMFY_OUTPUT", r"A:\Users\rhine\ComfyUI-Shared\output"))
JOB_DIR = ROOT / "live_jobs" / "voice_bootstrap_20260918"
OUT_JSON = JOB_DIR / "live_voice_bootstrap_report.json"
JOB_ID = "backrooms_voice_bootstrap"
CHAR = "ACTOR"
BOOT_LINE = "Hi, thanks for having me."
DEP_LINE = "Okay, that was better in my head."
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


def loaders():
    return {
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
        print(f"SUBMIT {name} prompt_id={pid}", flush=True)
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
        return {
            "name": name,
            "ok": False,
            "error": str(e)[:1500],
            "wall_clock_s": round(time.time() - t0, 2),
            "peak_mib": peak,
        }


def find_saved_mp4(hist_outputs, prefix_subdir: str) -> Path:
    """Locate newest mp4 under Shared output matching prefix."""
    # Prefer history filenames when present
    candidates: list[Path] = []
    if isinstance(hist_outputs, dict):
        for node_out in hist_outputs.values():
            if not isinstance(node_out, dict):
                continue
            for key in ("gifs", "videos", "images"):
                for item in node_out.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    fn = item.get("filename")
                    sub = item.get("subfolder") or ""
                    if fn and str(fn).lower().endswith(".mp4"):
                        candidates.append(SHARED_OUTPUT / sub / fn)
    folder = SHARED_OUTPUT / prefix_subdir
    if folder.is_dir():
        candidates.extend(folder.glob("*.mp4"))
    existing = [p for p in candidates if p.is_file()]
    if not existing:
        raise FileNotFoundError(f"no mp4 under {prefix_subdir} / history")
    return max(existing, key=lambda p: p.stat().st_mtime)


def has_audio_stream(mp4: Path) -> bool:
    cp = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "csv=p=0",
            str(mp4),
        ],
        capture_output=True,
        text=True,
    )
    return bool(cp.stdout.strip())


def extract_wav(mp4: Path, wav: Path) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    cp = subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4), "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(wav)],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0 or not wav.is_file() or wav.stat().st_size < 1000:
        raise RuntimeError(cp.stderr[-1500:] or "ffmpeg extract failed")


def build_ref2va_graph(
    *,
    img: str,
    voice_wav: str,
    character_id: str,
    spoken_line: str,
    filename_prefix: str,
    seed: int,
):
    plan = ggb.RefBindingPlan(
        images=[ggb.ImageRef(img, character_id=character_id, role="identity")],
        audios=[
            ggb.AudioRef(voice_wav, character_id=character_id, exact_transcript=spoken_line),
        ],
    )
    prompt = (
        f"One character speaks on camera. Locked medium shot. Subtle motion. No text. "
        f'The character says exactly: "{spoken_line}"'
    )
    g = {
        **loaders(),
        "33": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "34": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "35": {
            "class_type": "BasicScheduler",
            "inputs": {"model": ["30", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0},
        },
    }
    g = ggb.apply_ref2va_autogrow(
        g,
        prompt=prompt,
        plan=plan,
        width=864,
        height=480,
        length=LENGTH,
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
            "filename_prefix": filename_prefix,
            "format": "mp4",
            "codec": "auto",
        },
    }
    return g, plan


def main() -> int:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    ver = (http_json("GET", "/system_stats").get("system") or {}).get("comfyui_version")
    img = "astra_live_continuity/frame_000.png"
    if not (SHARED_INPUT / img).is_file():
        raise FileNotFoundError(img)

    # Disposable conditioner seed (NOT the canonical lock). Prefer ALICE wav as throwaway seed.
    seed_rel = "astra_voice_ALICE.wav"
    seed_path = SHARED_INPUT / seed_rel
    if not seed_path.is_file():
        seed_path = SHARED_INPUT / Path(seed_rel).name
        seed_rel = seed_path.name
    if not seed_path.is_file():
        raise FileNotFoundError("need a disposable seed wav for bootstrap Ref2VA conditioner")

    seed_hash = sha256_file(seed_path)
    dialogue_index = {
        "C001": [{"speaker_id": CHAR, "text": BOOT_LINE}],
        "C002": [{"speaker_id": CHAR, "text": DEP_LINE}],
    }
    # Store on disk for restart-preservation check within this job
    db_path = JOB_DIR / "voice_bootstrap.sqlite"
    if db_path.exists():
        db_path.unlink()
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    nvc.ensure_voice_schema(db)

    # Dependent before lock must fail
    blocked_ok = False
    try:
        nvc.require_canonical_voices_for_shot(
            db,
            job_id=JOB_ID,
            shot_id="C002",
            dialogue_lines=dialogue_index["C002"],
            shot_dialogue_index=dialogue_index,
        )
    except nvc.NativeVoiceError:
        blocked_ok = True

    # --- Bootstrap take ---
    g1, plan1 = build_ref2va_graph(
        img=img,
        voice_wav=seed_rel,
        character_id=CHAR,
        spoken_line=BOOT_LINE,
        filename_prefix="astra_voice_bootstrap/boot_c001",
        seed=101,
    )
    # Confirm seed is what graph loads (not yet canonical)
    assert g1["9100"]["inputs"]["audio"] == seed_rel
    r1 = run("voice_boot_c001", g1)
    if not r1.get("ok"):
        report = {"ok": False, "stage": "bootstrap_render", "result": r1, "comfyui_version": ver}
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        return 1

    boot_mp4 = find_saved_mp4(r1.get("outputs"), "astra_voice_bootstrap")
    if not has_audio_stream(boot_mp4):
        raise RuntimeError(f"bootstrap mp4 missing audio: {boot_mp4}")

    extracted = JOB_DIR / "extracted" / "ACTOR_bootstrap_take.wav"
    extract_wav(boot_mp4, extracted)
    # Copy into Comfy input under character-scoped name (never C001_master_voice)
    comfy_voice_rel = "astra_voice_bootstrap/ACTOR_canonical_from_take.wav"
    comfy_voice_path = SHARED_INPUT / comfy_voice_rel
    comfy_voice_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(extracted, comfy_voice_path)
    locked_hash = sha256_file(comfy_voice_path)
    if locked_hash == seed_hash:
        # Extremely unlikely if take differs; still legal but note
        pass

    nvc.assert_not_global_c001_voice(CHAR, str(comfy_voice_path))
    cand = nvc.register_candidate(
        db,
        candidate_id="cand_ACTOR_boot",
        job_id=JOB_ID,
        character_id=CHAR,
        bootstrap_shot_id="C001",
        bootstrap_attempt_id=str(r1.get("prompt_id")),
        source_audio_path=boot_mp4,
        segment_start_sample=0,
        segment_end_sample=max(16000, extracted.stat().st_size),
        reference_audio_path=comfy_voice_path,
        exact_reference_transcript=BOOT_LINE,
        qa_evidence={
            "source": "extracted_from_first_minimax_take",
            "bootstrap_mp4": str(boot_mp4),
            "disposable_seed_wav": seed_rel,
            "disposable_seed_hash": seed_hash,
            "seed_is_not_canonical": True,
            "audio_stream_present": True,
            "spoken_line": BOOT_LINE,
        },
    )
    rec = nvc.promote_canonical(
        db, job_id=JOB_ID, character_id=CHAR, candidate_id="cand_ACTOR_boot"
    )
    db.commit()

    # Restart preservation: reopen DB
    db.close()
    db = sqlite3.connect(str(db_path))
    db.row_factory = sqlite3.Row
    rec2 = nvc.get_canonical_voice(db, job_id=JOB_ID, character_id=CHAR)
    if rec2 is None or rec2.reference_audio_hash != locked_hash:
        raise RuntimeError("canonical voice not preserved across DB reopen")

    # Refuse silent replace with different take
    replace_blocked = False
    try:
        # fake other candidate with different file if needed
        other = JOB_DIR / "extracted" / "decoy.wav"
        if not other.exists():
            shutil.copy2(seed_path, other)
        nvc.register_candidate(
            db,
            candidate_id="cand_ACTOR_later",
            job_id=JOB_ID,
            character_id=CHAR,
            bootstrap_shot_id="C001",
            bootstrap_attempt_id="later",
            source_audio_path=other,
            segment_start_sample=0,
            segment_end_sample=max(1000, other.stat().st_size),
            reference_audio_path=other,
            exact_reference_transcript=BOOT_LINE,
            qa_evidence={"note": "should_not_replace"},
        )
        nvc.promote_canonical(
            db, job_id=JOB_ID, character_id=CHAR, candidate_id="cand_ACTOR_later", allow_replace=False
        )
    except nvc.NativeVoiceError:
        replace_blocked = True

    # --- Dependent take (must use locked hash path) ---
    nvc.require_canonical_voices_for_shot(
        db,
        job_id=JOB_ID,
        shot_id="C002",
        dialogue_lines=dialogue_index["C002"],
        shot_dialogue_index=dialogue_index,
    )
    g2, plan2 = build_ref2va_graph(
        img=img,
        voice_wav=comfy_voice_rel,
        character_id=CHAR,
        spoken_line=DEP_LINE,
        filename_prefix="astra_voice_bootstrap/dep_c002",
        seed=202,
    )
    if g2["9100"]["inputs"]["audio"] != comfy_voice_rel:
        raise RuntimeError("dependent graph did not bind canonical voice path")
    r2 = run("voice_dep_c002", g2)
    if not r2.get("ok"):
        report = {
            "ok": False,
            "stage": "dependent_render",
            "bootstrap": r1,
            "result": r2,
            "canonical_hash": locked_hash,
        }
        OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2), flush=True)
        return 1

    dep_mp4 = find_saved_mp4(r2.get("outputs"), "astra_voice_bootstrap")
    # Prefer newer dep file
    dep_candidates = sorted(
        (SHARED_OUTPUT / "astra_voice_bootstrap").glob("dep_c002*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if dep_candidates:
        dep_mp4 = dep_candidates[0]
    if not has_audio_stream(dep_mp4):
        raise RuntimeError(f"dependent mp4 missing audio: {dep_mp4}")

    report = {
        "ok": True,
        "comfyui_version": ver,
        "job_id": JOB_ID,
        "character_id": CHAR,
        "blocked_dependent_before_lock": blocked_ok,
        "refuse_canonical_replace": replace_blocked,
        "disposable_seed": {"path": seed_rel, "sha256": seed_hash, "is_canonical": False},
        "bootstrap": {
            "shot": "C001",
            "line": BOOT_LINE,
            "mp4": str(boot_mp4),
            "has_audio": True,
            "result": {k: v for k, v in r1.items() if k != "outputs"},
            "extracted_wav": str(extracted),
            "canonical_comfy_input": comfy_voice_rel,
            "canonical_sha256": locked_hash,
            "candidate": cand,
            "canonical_record": rec.to_dict(),
        },
        "dependent": {
            "shot": "C002",
            "line": DEP_LINE,
            "mp4": str(dep_mp4),
            "has_audio": True,
            "load_audio_path": g2["9100"]["inputs"]["audio"],
            "load_audio_matches_canonical": g2["9100"]["inputs"]["audio"] == comfy_voice_rel,
            "bound_hash_matches_lock": sha256_file(SHARED_INPUT / comfy_voice_rel) == locked_hash,
            "result": {k: v for k, v in r2.items() if k != "outputs"},
        },
        "restart_preserved_hash": rec2.reference_audio_hash,
        "notes": (
            "Bootstrap used a disposable seed WAV as Ref2VA conditioner only. "
            "Canonical lock is the extracted audio from the first MiniMax take. "
            "Dependent shot bound that exact file/hash. Not a full 102-shot soak."
        ),
    }
    ok = (
        report["ok"]
        and blocked_ok
        and replace_blocked
        and report["dependent"]["load_audio_matches_canonical"]
        and report["dependent"]["bound_hash_matches_lock"]
        and locked_hash == rec2.reference_audio_hash
    )
    report["ok"] = bool(ok)
    OUT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
