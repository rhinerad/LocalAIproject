#!/usr/bin/env python3
"""Turn the operator's chosen audition takes into voice masters.

USAGE
-----
The operator listens to the takes in `story/AUDITION_<slug>/` and records their
choice — either by editing `chosen` in `voice_audition_manifest.json`, or here:

    python work\\install_audition_winners.py --pick Kent=2 --pick Avery=1
    python work\\install_audition_winners.py --apply

`--pick NAME=TAKE` records a choice. `--apply` cuts and installs every recorded
choice. They can be combined.

WHAT IT DOES PER WINNER
-----------------------
1. Extracts the audio from that take's MP4.
2. Removes the leading 'hmpf' burst, measured per file — 12 of 16 known-good
   takes carry one, and trim points range 0.38-1.60 s, so a flat one-second cut
   is wrong in both directions. Same detector as
   `work/harvest_good_audio_masters.py`.
3. Cuts ONE CONTIGUOUS PASSAGE, first word to last word, pauses left in.
   Never stitched — CLAUDE.md forbids joining passages.
4. Writes `outputs/equal_shares/voices/<slug>/omni_master_audition_vN.wav` as a
   NEW VERSION. Nothing is ever overwritten.
5. Reports speech density so a master that is really noise cannot slip through
   silently — this project has already shipped one that was road noise.

WHAT IT DOES NOT DO
-------------------
Judge the voice. It cannot hear. It installs what the operator picked and flags
anything mechanically suspect (under 6 s, or low speech density) rather than
rejecting it.

AFTER THIS
----------
    python work\\sync_omni_audio_config.py      # wire the new masters in
    python work\\build_native_r2v_prompts.py    # regenerate prompts against them
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
EQ = ROOT / "outputs" / "equal_shares"
MANIFEST = EQ / "voice_audition_manifest.json"
VOICES = EQ / "voices"

SR = 24000
TARGET_SECONDS = 6.0
DENSITY_FLOOR = 0.55        # below this, say so loudly


def _harvest():
    """Reuse the measured trim/analysis from the good-audio harvester."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hg", ROOT / "work" / "harvest_good_audio_masters.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def next_version(folder: Path, stem: str) -> Path:
    n = 1
    while (folder / f"{stem}_v{n}.wav").exists():
        n += 1
    return folder / f"{stem}_v{n}.wav"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pick", action="append", default=[],
                    help="NAME=TAKE, e.g. --pick Kent=2")
    ap.add_argument("--apply", action="store_true",
                    help="cut and install every recorded choice")
    args = ap.parse_args()

    if not MANIFEST.is_file():
        print(f"no {MANIFEST} — run work/render_voice_auditions.py first")
        return 2
    man = json.loads(MANIFEST.read_text(encoding="utf-8-sig"))

    for spec in args.pick:
        if "=" not in spec:
            print(f"bad --pick {spec!r}; expected NAME=TAKE")
            return 2
        name, take = spec.rsplit("=", 1)
        match = next((k for k in man["characters"] if k.lower() == name.strip().lower()), None)
        if not match:
            print(f"no audition for {name!r}. Have: {', '.join(sorted(man['characters']))}")
            return 2
        man["characters"][match]["chosen"] = int(take)
        man["characters"][match]["status"] = "chosen"
        print(f"recorded: {match} -> take {take}")
    if args.pick:
        MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")

    pending = {k: v for k, v in man["characters"].items() if v.get("chosen")}
    unchosen = [k for k, v in man["characters"].items() if not v.get("chosen")]
    print(f"\nchosen: {len(pending)}   still awaiting a choice: {len(unchosen)}"
          + (f"  {unchosen}" if unchosen else ""))
    if not args.apply:
        print("\n--apply not given; nothing installed")
        return 0

    hg = _harvest()
    installed, flagged = [], []
    for name, rec in pending.items():
        take = next((t for t in rec["takes"] if t["take"] == rec["chosen"]), None)
        if not take or not take.get("source_video"):
            print(f"{name}: take {rec['chosen']} has no rendered video — skipped")
            continue
        src = Path(take["source_video"])
        if not src.is_file():
            print(f"{name}: {src} missing — skipped")
            continue

        a = hg.load_mono(src, SR)
        meas = hg.analyse(a, SR)
        trimmed = a[int(meas["trim_seconds"] * SR):]
        runs = hg.speech_runs(trimmed, SR)
        if not runs:
            print(f"{name}: NO SPEECH DETECTED in the chosen take — not installed")
            flagged.append(name)
            continue
        s, e = runs[0][0], runs[-1][1]
        seg = trimmed[int(max(0, s - 0.08) * SR):int(min(len(trimmed) / SR, e + 0.08) * SR)]
        secs = len(seg) / SR
        speech = sum(y - x for x, y in runs)
        density = speech / (e - s) if e > s else 0.0

        folder = VOICES / rec["slug"]
        folder.mkdir(parents=True, exist_ok=True)
        dest = next_version(folder, "omni_master_audition")
        sf.write(dest, seg, SR, subtype="PCM_16")

        note = []
        if secs < TARGET_SECONDS:
            note.append(f"SHORT ({secs:.2f}s < {TARGET_SECONDS}s target)")
        if density < DENSITY_FLOOR:
            note.append(f"LOW DENSITY ({density:.0%})")
        rec.update(installed_master=str(dest), master_seconds=round(secs, 2),
                   speech_density=round(density, 3),
                   short_master=secs < TARGET_SECONDS,
                   leading_artifact_trimmed=meas["trim_seconds"],
                   status="installed_pending_ear_confirmation")
        installed.append((name, dest, secs, density, note))
        if note:
            flagged.append(name)

    MANIFEST.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f'\n{"character":22s}{"secs":>7}{"density":>9}  file')
    print("-" * 92)
    for name, dest, secs, density, note in installed:
        print(f'{name:22s}{secs:7.2f}{density:9.0%}  {dest.name}'
              + ("   <- " + "; ".join(note) if note else ""))
    print(f"\ninstalled {len(installed)} masters as new versions; nothing overwritten")
    if flagged:
        print(f"flagged for a listen: {flagged}")
    print("\nNEXT:\n  python work\\sync_omni_audio_config.py"
          "\n  python work\\build_native_r2v_prompts.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
