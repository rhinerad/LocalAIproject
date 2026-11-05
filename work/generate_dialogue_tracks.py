#!/usr/bin/env python3
"""Generate consistent post-production dialogue from the edited story config."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import torch
from kokoro import KModel, KPipeline


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
CONFIG_PATH = PROJECT / "story_config.json"
MODEL_ROOT = Path(r"A:\Users\rhine\ComfyUI-Shared\models\Kokorotts\Kokoro-82M")
OUTPUT = PROJECT / "audio" / "dialogue"
VOICE_ROOT = MODEL_ROOT / "voices"
SAMPLE_RATE = 24000

VOICE_MAP = {
    "Narrator": "am_onyx.pt",
    "Kent": "am_michael.pt",
    "Avery": "bm_george.pt",
    "Doris": "af_heart.pt",
    "Ryann Sally": "af_nicole.pt",
    "Faith White": "bm_daniel.pt",
    "Wealthy commuter": "am_eric.pt",
    "Unhoused man": "bm_lewis.pt",
    "Terminal voice": "af_sky.pt",
    "Volunteer": "af_alloy.pt",
    "Housing representative": "af_sarah.pt",
    "Congregation member": "am_adam.pt",
    "Council member": "am_eric.pt",
    "Crew lead": "bm_fable.pt",
    "Aid worker": "af_bella.pt",
}


def spoken_text(line: str) -> str:
    quotes = re.findall(r"[“\"]([^”\"]+)[”\"]", line)
    if quotes:
        return " ".join(quotes).strip()
    return line.split(":", 1)[1].strip() if ":" in line else line.strip()


def speaker_name(line: str) -> str:
    direction = line.split(":", 1)[0].strip()
    return direction.split(",", 1)[0].strip()


def write_wav(path: Path, samples: np.ndarray):
    samples = np.nan_to_num(samples.astype(np.float32))
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0.98:
        samples = samples * (0.98 / peak)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())


def duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def fit_to_window(source: Path, destination: Path, window: float):
    actual = duration(source)
    if actual <= window * 0.97:
        shutil.copy2(source, destination)
        return actual, actual
    tempo = actual / max(0.2, window * 0.97)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", f"atempo={tempo:.8f}", str(destination)],
        check=True,
    )
    return actual, duration(destination)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", action="append", help="generate one clip id; repeat as needed")
    args = parser.parse_args()
    requested = set(args.only or [])
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)

    model = KModel(config=MODEL_ROOT / "config.json", model=MODEL_ROOT / "kokoro-v1_0.pth").to("cpu").eval()
    pipelines = {}
    voice_tensors = {}
    records = []
    for clip in config["clips"]:
        if requested and clip["id"] not in requested:
            continue
        for line_index, timing in enumerate(clip.get("dialogue_timing", []), 1):
            line = str(timing["line"])
            speaker = speaker_name(line)
            text = spoken_text(line)
            voice = VOICE_MAP.get(speaker, "af_alloy.pt" if speaker in {"Doris", "Ryann Sally"} else "am_eric.pt")
            lang = "b" if voice.startswith(("bf_", "bm_")) else "a"
            if lang not in pipelines:
                pipelines[lang] = KPipeline(lang_code=lang, repo_id=None, model=model)
            if voice not in voice_tensors:
                voice_tensors[voice] = torch.load(VOICE_ROOT / voice, weights_only=True, map_location="cpu")
            window = float(timing["end"]) - float(timing["start"])
            word_rate = len(re.findall(r"\b[\w']+\b", text)) / max(window, 0.5)
            speed = min(1.35, max(0.88, word_rate / 2.55))
            chunks = []
            for _, _, audio in pipelines[lang](text, voice=voice_tensors[voice], speed=speed, split_pattern=r"\n+"):
                chunks.append(np.asarray(audio, dtype=np.float32))
            if not chunks:
                raise RuntimeError(f"Kokoro returned no audio for {clip['id']} line {line_index}")
            raw = OUTPUT / f"{clip['id']}_{line_index:02d}_{speaker.replace(' ', '_')}_raw.wav"
            fitted = OUTPUT / f"{clip['id']}_{line_index:02d}_{speaker.replace(' ', '_')}.wav"
            write_wav(raw, np.concatenate(chunks))
            raw_seconds, fitted_seconds = fit_to_window(raw, fitted, window)
            raw.unlink(missing_ok=True)
            records.append({
                "clip_id": clip["id"],
                "line_index": line_index,
                "speaker": speaker,
                "voice": voice,
                "text": text,
                "start": float(timing["start"]),
                "end": float(timing["end"]),
                "window_seconds": window,
                "generated_seconds": round(raw_seconds, 4),
                "fitted_seconds": round(fitted_seconds, 4),
                "wav": str(fitted),
            })
            print(f"{clip['id']} {speaker}: {fitted_seconds:.2f}s / {window:.2f}s", flush=True)

    manifest_path = PROJECT / "audio" / ("dialogue_manifest.json" if not requested else "dialogue_manifest_partial.json")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"sample_rate": SAMPLE_RATE, "voices": VOICE_MAP, "segments": records}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print("MANIFEST", manifest_path)


if __name__ == "__main__":
    main()
