"""Convert remaining Narrator Kokoro WAVs to RVC using narrator_equal_shares_100e.pth.

Run from project root with dbz-rvc-env:
    $DBZ_PY = "A:/Users/rhine/ComfyUI-Shared/tools/dbz-rvc-env/python.exe"
    & $DBZ_PY work/convert_narrator_rvc_batch.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJ_ROOT = Path(__file__).resolve().parents[1]
APPLIO    = Path("A:/Users/rhine/ComfyUI-Shared/tools/applio")
DIALOGUE  = PROJ_ROOT / "outputs/equal_shares/audio/dialogue"

PTH_PATH   = str(APPLIO / "logs/narrator_equal_shares/narrator_equal_shares_100e.pth")
INDEX_PATH = str(APPLIO / "logs/narrator_equal_shares/narrator_equal_shares.index")

# Lines to convert — 00A already done
LINES = [
    "00B_01_Narrator",
    "00C_01_Narrator",
    "00D_01_Narrator",
    "00D2_01_Narrator",
    "00E_01_Narrator",
    "00F_01_Narrator",
    "00G_01_Narrator",
    "00I_01_Narrator",
]

TOLERANCE_S = 0.15


def wav_duration(path: Path) -> float | None:
    import re
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def convert_one(stem: str) -> tuple[bool, float]:
    """Convert one WAV. Returns (ok, delta_seconds)."""
    in_wav  = DIALOGUE / f"{stem}.wav"
    out_wav = DIALOGUE / f"{stem}_rvc.wav"

    if not in_wav.exists():
        print(f"  [SKIP] {stem}: input not found")
        return False, 0.0

    code = "\n".join([
        "import sys, os",
        f"sys.path.insert(0, {str(APPLIO)!r})",
        f"os.chdir({str(APPLIO)!r})",
        "from core import run_infer_script",
        "result = run_infer_script(",
        "    pitch=0,",
        "    index_rate=0.75,",
        "    volume_envelope=1.0,",
        "    protect=0.45,",
        f"    f0_method='rmvpe',",
        f"    input_path={str(in_wav)!r},",
        f"    output_path={str(out_wav)!r},",
        f"    pth_path={PTH_PATH!r},",
        f"    index_path={INDEX_PATH!r},",
        "    split_audio=True,",
        "    f0_autotune=False,",
        "    f0_autotune_strength=1.0,",
        "    proposed_pitch=False,",
        "    proposed_pitch_threshold=255.0,",
        "    clean_audio=True,",
        "    clean_strength=0.5,",
        "    export_format='WAV',",
        "    embedder_model='contentvec',",
        "    embedder_model_custom=None,",
        "    sid=0,",
        ")",
        "print('[INFER RESULT]', result)",
    ])

    r = subprocess.run([sys.executable, "-c", code], cwd=str(APPLIO))
    if r.returncode != 0 or not out_wav.exists():
        print(f"  [FAIL] {stem}: conversion error (exit {r.returncode})")
        return False, 0.0

    in_dur  = wav_duration(in_wav)
    out_dur = wav_duration(out_wav)
    if in_dur is None or out_dur is None:
        print(f"  [FAIL] {stem}: could not measure duration")
        return False, 0.0

    delta = abs(out_dur - in_dur)
    status = "OK" if delta <= TOLERANCE_S else "FAIL-DELTA"
    print(f"  [{status}] {stem}: in={in_dur:.3f}s out={out_dur:.3f}s delta={delta:.4f}s")
    return delta <= TOLERANCE_S, delta


def main() -> None:
    print("=== Narrator RVC Batch Conversion ===")
    print(f"  Model: narrator_equal_shares_100e.pth")
    print(f"  Tolerance: +-{TOLERANCE_S}s\n")

    results: list[dict] = []

    for stem in LINES:
        print(f"\nConverting {stem}...")
        ok, delta = convert_one(stem)
        results.append({"stem": stem, "ok": ok, "delta": delta})

    print("\n=== Summary ===")
    passed = [r for r in results if r["ok"]]
    failed = [r for r in results if not r["ok"]]
    for r in results:
        mark = "OK  " if r["ok"] else "FAIL"
        print(f"  [{mark}] {r['stem']}  delta={r['delta']:.4f}s")

    print(f"\n{len(passed)}/{len(results)} passed duration check.")
    if failed:
        print("FAILED:")
        for r in failed:
            print(f"  {r['stem']}")
        sys.exit(1)
    else:
        print("All conversions within tolerance. Ready to build review cut.")


if __name__ == "__main__":
    main()
