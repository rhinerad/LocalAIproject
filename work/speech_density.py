#!/usr/bin/env python3
"""Measure how much of an audio file is actually SPEECH, not merely loud.

Why this exists
---------------
The first pass at building voice references checked mean dB across the window
and passed everything. That check is worthless here, for two separate reasons
found by listening:

  * A window that is 3 s of speech and 12 s of silence has a respectable mean.
  * Kent's reference came from `14D`, the driving clip. It measured -19.9 dB
    mean and 100% "voiced" under a -35 dB silence gate, because road and engine
    noise never drops below the gate. It is continuous noise with a little
    dialogue on top.

So level tells you nothing. This module scores speech directly, using two
properties that separate voice from broadband or low-frequency noise:

  1. **Band ratio.** Speech puts most of its energy in roughly 300-3400 Hz.
     Engine rumble is dominated below 300 Hz; hiss is flat and wide.
  2. **Syllable modulation.** The loudness envelope of speech fluctuates at
     about 4-8 Hz, one syllable at a time. Steady noise has almost no energy in
     that band; music tends to modulate slower and more regularly.

Neither is sufficient alone. A frame counts as speech only if both hold, which
is what stops a car interior from reading as a voice.

CALIBRATION
-----------
Thresholds were swept against known ground truth rather than guessed:

  positive  Kokoro TTS lines (pure clean speech)      want > 0.85
  positive  1.mp4, MiniMax_H3_00002_.mp4 (real takes) want > 0.40
  negative  Kent's 14D window (car interior)          want < 0.30

The chosen values give 0.82-0.87 on Kokoro, 0.56-0.76 on real takes, and 0.20 on
Kent's driving clip. An earlier setting of BAND_RATIO_MIN=0.45 scored the Kokoro
file at 0.35, because a deep male voice puts a lot of energy below 300 Hz in the
fundamental and its low harmonics. That is why the band gate sits at 0.25.

The syllable-modulation gate is computed but **disabled by default**
(MOD_RATIO_MIN = 0.0): at any threshold high enough to matter it also rejected
genuine speech. The band ratio alone separates voice from engine noise cleanly
here. Raise it if music ever needs excluding, and re-run the calibration set.

To re-calibrate, score the three groups above and pick thresholds that keep the
positives high and the negative low. Do not tune against a single file.

No downloads. numpy only.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

FRAME = 0.025          # 25 ms analysis frame
HOP = 0.010            # 10 ms hop
SPEECH_LO, SPEECH_HI = 300.0, 3400.0
BAND_RATIO_MIN = 0.25  # fraction of 50-8000 Hz energy inside the speech band
MOD_LO, MOD_HI = 3.0, 9.0
MOD_RATIO_MIN = 0.00   # disabled by default -- see CALIBRATION below
REL_FLOOR_DB = 35.0    # frames this far below the file's peak are not speech
MIN_RUN = 0.20         # ignore speech runs shorter than this
BRIDGE_GAP = 0.50      # join two runs separated by less than this


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    """Read any container to mono float via ffmpeg, or a WAV directly."""
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path)) as w:
                sr = w.getframerate()
                raw = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
                a = raw.astype(np.float32) / 32768.0
                if w.getnchannels() == 2:
                    a = a.reshape(-1, 2).mean(axis=1)
                return a, sr
        except Exception:
            pass
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
         "-ac", "1", "-ar", "16000", "-"],
        capture_output=True,
    )
    if p.returncode:
        raise RuntimeError(f"ffmpeg failed on {path}: {p.stderr.decode()[:200]}")
    return np.frombuffer(p.stdout, dtype=np.float32), 16000


def speech_mask(a: np.ndarray, sr: int) -> tuple[np.ndarray, float]:
    """Per-frame boolean: is this frame speech? Returns (mask, hop_seconds)."""
    n = int(FRAME * sr)
    hop = int(HOP * sr)
    if len(a) < n * 4:
        return np.zeros(0, dtype=bool), HOP

    frames = np.lib.stride_tricks.sliding_window_view(a, n)[::hop]
    win = np.hanning(n)
    spec = np.abs(np.fft.rfft(frames * win, axis=1))
    freqs = np.fft.rfftfreq(n, 1 / sr)

    full = (freqs >= 50) & (freqs <= 8000)
    band = (freqs >= SPEECH_LO) & (freqs <= SPEECH_HI)
    e_full = (spec[:, full] ** 2).sum(axis=1) + 1e-12
    e_band = (spec[:, band] ** 2).sum(axis=1)
    band_ratio = e_band / e_full

    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    loud = db > (db.max() - REL_FLOOR_DB)

    # Syllable-rate modulation of the envelope, measured over a moving second.
    env = rms - rms.mean()
    fps = 1.0 / HOP
    w = int(fps)  # 1 second
    mod = np.zeros(len(env))
    for i in range(0, len(env), w // 2 or 1):
        seg = env[i:i + w]
        if len(seg) < w // 2:
            break
        sp = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        f = np.fft.rfftfreq(len(seg), HOP)
        tot = (sp ** 2).sum() + 1e-12
        syl = (sp[(f >= MOD_LO) & (f <= MOD_HI)] ** 2).sum()
        mod[i:i + w] = syl / tot

    return loud & (band_ratio >= BAND_RATIO_MIN) & (mod >= MOD_RATIO_MIN), HOP


def runs_from_mask(mask: np.ndarray, hop: float) -> list[tuple[float, float]]:
    """Contiguous speech spans, with short gaps bridged and short runs dropped."""
    if not mask.any():
        return []
    idx = np.flatnonzero(np.diff(np.concatenate(([0], mask.view(np.int8), [0]))))
    spans = [(a * hop, b * hop) for a, b in idx.reshape(-1, 2)]
    merged = [list(spans[0])]
    for s, e in spans[1:]:
        if s - merged[-1][1] <= BRIDGE_GAP:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged if e - s >= MIN_RUN]


def longest_passage(
    mask: np.ndarray,
    hop: float,
    max_gap: float = 1.0,
    min_density: float = 0.6,
    min_seconds: float = 2.0,
) -> tuple[float, float, float]:
    """Longest span of CONTINUOUS speaking. Returns (start, end, density).

    A voice reference has to be one unbroken passage from one take. Splicing two
    passages -- even from the same clip -- risks teaching the model an average of
    two deliveries, which is the drift the reference exists to prevent.

    "Continuous" is not the same as "no silence". Natural speech contains breath
    pauses and sentence gaps; cutting at every one of those would leave 2-second
    fragments. So a passage may contain internal gaps up to `max_gap`, but the
    whole span must still be at least `min_density` speech. That combination is
    what separates 'someone talking' from 'someone who said two words, waited
    six seconds, then said two more'.
    """
    spans = runs_from_mask(mask, hop)
    if not spans:
        return 0.0, 0.0, 0.0

    best = (0.0, 0.0, 0.0)
    for i in range(len(spans)):
        start = spans[i][0]
        speech = 0.0
        end = spans[i][1]
        for j in range(i, len(spans)):
            if j > i and spans[j][0] - spans[j - 1][1] > max_gap:
                break
            speech += spans[j][1] - spans[j][0]
            end = spans[j][1]
            total = end - start
            density = speech / total if total else 0.0
            if total >= min_seconds and density >= min_density and total > best[1] - best[0]:
                best = (start, end, density)
    return best


def analyse(path: Path) -> dict:
    a, sr = read_audio(path)
    dur = len(a) / sr if sr else 0.0
    mask, hop = speech_mask(a, sr)
    spans = runs_from_mask(mask, hop)
    speech = sum(e - s for s, e in spans)
    best = max(spans, key=lambda x: x[1] - x[0], default=(0.0, 0.0))
    return {
        "file": str(path),
        "duration": round(dur, 2),
        "speech_seconds": round(speech, 2),
        "speech_fraction": round(speech / dur, 3) if dur else 0.0,
        "longest_run": round(best[1] - best[0], 2),
        "longest_run_start": round(best[0], 2),
        "longest_run_end": round(best[1], 2),
        "spans": [(round(s, 2), round(e, 2)) for s, e in spans],
    }


def verdict(r: dict) -> str:
    if r["speech_seconds"] >= 6.0:
        return "OK"
    if r["speech_seconds"] >= 2.5:
        return "THIN"
    return "UNUSABLE"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    out = []
    for pat in args.paths:
        for p in sorted(Path().glob(pat)) if any(c in pat for c in "*?[") else [Path(pat)]:
            if not p.exists():
                print(f"missing: {p}", file=sys.stderr)
                continue
            try:
                r = analyse(p)
            except Exception as e:
                print(f"{p}: {e}", file=sys.stderr)
                continue
            r["verdict"] = verdict(r)
            out.append(r)

    if args.json:
        print(json.dumps(out, indent=2))
        return 0

    print(f"{'file':44s} {'dur':>6} {'speech':>7} {'frac':>6} {'run':>6}  verdict")
    for r in sorted(out, key=lambda x: x["speech_seconds"]):
        name = r["file"]
        if len(name) > 44:
            name = "…" + name[-43:]
        print(f'{name:44s} {r["duration"]:6.1f} {r["speech_seconds"]:7.1f} '
              f'{r["speech_fraction"]:5.0%} {r["longest_run"]:6.1f}  {r["verdict"]}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
