"""Train an RVC voice model for the Narrator and convert one Kokoro line.

This is the Task-2 / Task-3 pilot. Run only after build_rvc_training_set.py
has produced:
    outputs/equal_shares/voices/narrator/rvc_training/all_speech.wav

Applio is at A:/Users/rhine/ComfyUI-Shared/tools/applio
Python env:  A:/Users/rhine/ComfyUI-Shared/tools/dbz-rvc-env/python.exe

Steps
-----
1.  Copy narrator all_speech.wav into a clean Applio dataset directory.
2.  Preprocess (segment + normalise).
3.  Extract features: pitch via harvest (no rmvpe download), embeddings via
    contentvec (already on disk at rvc/models/embedders/contentvec/).
4.  Train for EPOCHS epochs.
5.  Convert outputs/equal_shares/audio/dialogue/00A_01_Narrator.wav
    → outputs/equal_shares/audio/dialogue/00A_01_Narrator_rvc.wav
6.  Verify output duration matches input to within 0.1 s.
7.  Print a duration report; stop there.

This script MUST be run from the project root:
    A:/Users/rhine/ComfyUI-Shared/tools/dbz-rvc-env/python.exe work/train_rvc_narrator.py

Or equivalently:
    $DBZ_PY = "A:/Users/rhine/ComfyUI-Shared/tools/dbz-rvc-env/python.exe"
    & $DBZ_PY work/train_rvc_narrator.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths

PROJ_ROOT  = Path(__file__).resolve().parents[1]
APPLIO     = Path("A:/Users/rhine/ComfyUI-Shared/tools/applio")
LOGS       = APPLIO / "logs"
MODELS_RVC = Path("A:/Users/rhine/ComfyUI-Shared/models/rvc")

NARRATOR_SEGMENTS_DIR = PROJ_ROOT / "outputs/equal_shares/voices/narrator/rvc_training/segments"
NARRATOR_TRAINING_WAV = PROJ_ROOT / "outputs/equal_shares/voices/narrator/rvc_training/all_speech.wav"
TARGET_KOKORO_WAV     = PROJ_ROOT / "outputs/equal_shares/audio/dialogue/00A_01_Narrator.wav"
OUTPUT_RVC_WAV        = PROJ_ROOT / "outputs/equal_shares/audio/dialogue/00A_01_Narrator_rvc.wav"

MODEL_NAME  = "narrator_equal_shares"
# Use the segments directory directly — Applio wants many short WAVs, not one big file
DATASET_DIR = NARRATOR_SEGMENTS_DIR

# ---------------------------------------------------------------------------
# Training parameters

SAMPLE_RATE = 40000    # Applio standard; 44100 WAVs are resampled during preprocess
CPU_CORES   = 4
GPU         = 0
EPOCHS      = 100      # pilot; enough to hear whether timbre transfer works
BATCH_SIZE  = 8
F0_METHOD   = "rmvpe"   # harvest not in this Applio build; rmvpe.pt already on disk (181 MB)
EMBEDDER    = "contentvec"       # already on disk at rvc/models/embedders/contentvec/

# ---------------------------------------------------------------------------

def check_preconditions() -> None:
    errors = []

    if not APPLIO.exists():
        errors.append(f"Applio not found at {APPLIO}")

    if not NARRATOR_SEGMENTS_DIR.exists() or not list(NARRATOR_SEGMENTS_DIR.glob("*.wav")):
        errors.append(
            f"Narrator segments missing: {NARRATOR_SEGMENTS_DIR}\n"
            "  Run: python work/build_rvc_training_set.py --character narrator"
        )

    if not TARGET_KOKORO_WAV.exists():
        errors.append(f"Kokoro source missing: {TARGET_KOKORO_WAV}")

    embedder_bin = APPLIO / "rvc/models/embedders/contentvec/pytorch_model.bin"
    if not embedder_bin.exists():
        errors.append(f"contentvec embedder missing: {embedder_bin}")

    if errors:
        for e in errors:
            print(f"[PRECONDITION FAIL] {e}")
        sys.exit(1)

    print("[OK] Preconditions passed")


def wav_duration_s(path: Path) -> float | None:
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


def prepare_dataset() -> None:
    """Report what training segments are available (segments dir is the dataset)."""
    wavs = sorted(NARRATOR_SEGMENTS_DIR.glob("*.wav"))
    total = sum(wav_duration_s(w) or 0 for w in wavs)
    print(f"Dataset: {NARRATOR_SEGMENTS_DIR}")
    print(f"  {len(wavs)} segment files, ~{total:.1f}s total")
    if not wavs:
        print("[ERROR] No WAV files in segments directory")
        sys.exit(1)


def run_applio(fn_name: str, **kwargs) -> str:
    """Call an Applio core function via a subprocess so CWD = applio root."""
    # Build a one-liner that imports core and calls the named function
    kw_repr = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
    code = (
        f"import sys; sys.path.insert(0, '.'); "
        f"import os; os.chdir({str(APPLIO)!r}); "
        f"from core import {fn_name}; "
        f"result = {fn_name}({kw_repr}); "
        f"print('[RESULT]', result)"
    )
    r = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(APPLIO),
        capture_output=False,   # let stdout/stderr stream to terminal
    )
    return "ok" if r.returncode == 0 else f"exit {r.returncode}"


def find_trained_model() -> tuple[Path, Path | None]:
    """Return (.pth path, .index path | None) for the trained model."""
    model_dir = LOGS / MODEL_NAME
    pth_files = sorted(model_dir.glob("*.pth"))
    if not pth_files:
        raise FileNotFoundError(f"No .pth found in {model_dir}")

    # Prefer the latest-epoch checkpoint
    def epoch_num(p: Path) -> int:
        import re
        m = re.search(r"_(\d+)e", p.name)
        return int(m.group(1)) if m else 0

    pth = sorted(pth_files, key=epoch_num)[-1]

    index_files = list(model_dir.glob("*.index"))
    index = index_files[0] if index_files else None

    return pth, index


def convert(pth: Path, index: Path | None) -> None:
    """Convert the Kokoro Narrator line with the trained model."""
    index_path = str(index) if index else ""

    # Use run_infer_script from Applio core — same pipeline as the NoUI interface
    code = "\n".join([
        "import sys, os",
        f"sys.path.insert(0, {str(APPLIO)!r})",
        f"os.chdir({str(APPLIO)!r})",
        "from core import run_infer_script",
        "result = run_infer_script(",
        f"    pitch=0,",
        f"    index_rate=0.75,",
        f"    volume_envelope=1.0,",
        f"    protect=0.45,",
        f"    f0_method={F0_METHOD!r},",
        f"    input_path={str(TARGET_KOKORO_WAV)!r},",
        f"    output_path={str(OUTPUT_RVC_WAV)!r},",
        f"    pth_path={str(pth)!r},",
        f"    index_path={index_path!r},",
        f"    split_audio=True,",
        f"    f0_autotune=False,",
        f"    f0_autotune_strength=1.0,",
        f"    proposed_pitch=False,",
        f"    proposed_pitch_threshold=255.0,",
        f"    clean_audio=True,",
        f"    clean_strength=0.5,",
        f"    export_format='WAV',",
        f"    embedder_model={EMBEDDER!r},",
        f"    embedder_model_custom=None,",
        f"    sid=0,",
        ")",
        "print('[INFER RESULT]', result)",
    ])

    print(f"\nConverting: {TARGET_KOKORO_WAV.name}")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(APPLIO))
    if r.returncode != 0:
        print(f"[ERROR] Conversion failed (exit {r.returncode})")
        sys.exit(1)


def verify_duration() -> None:
    """Check that output duration matches input within 0.1 s."""
    in_dur  = wav_duration_s(TARGET_KOKORO_WAV)
    out_dur = wav_duration_s(OUTPUT_RVC_WAV)

    print("\n=== Duration Verification ===")
    print(f"  Input  {TARGET_KOKORO_WAV.name}: {in_dur:.4f}s")
    print(f"  Output {OUTPUT_RVC_WAV.name}: {out_dur:.4f}s")

    if in_dur is None or out_dur is None:
        print("[ERROR] Could not measure duration — check ffprobe")
        sys.exit(1)

    diff = abs(out_dur - in_dur)
    if diff <= 0.1:
        print(f"  Duration match: delta={diff:.4f}s OK")
    else:
        print(f"  [FAIL] Duration mismatch: delta={diff:.4f}s — timeline would shift")
        print("  Do not batch-convert the 113 lines until this is resolved.")
        sys.exit(1)


def main() -> None:
    t0 = time.time()

    print("=== Narrator RVC Pilot ===")
    print(f"  Model:    {MODEL_NAME}")
    print(f"  Epochs:   {EPOCHS}")
    print(f"  F0:       {F0_METHOD}  (rmvpe.pt confirmed on disk, 181 MB)")
    print(f"  Embedder: {EMBEDDER}   (contentvec already on disk)")
    print()

    check_preconditions()
    prepare_dataset()

    # ---- 1. Preprocess ----
    print(f"\n--- Step 1: Preprocess ({SAMPLE_RATE}Hz) ---")
    run_applio(
        "run_preprocess_script",
        model_name=MODEL_NAME,
        dataset_path=str(DATASET_DIR),
        sample_rate=SAMPLE_RATE,
        cpu_cores=CPU_CORES,
        cut_preprocess="Automatic",
        process_effects=False,
        noise_reduction=False,
        clean_strength=0.5,
        chunk_len=3.0,
        overlap_len=0.3,
        normalization_mode="none",
    )

    # ---- 2. Feature extraction ----
    print(f"\n--- Step 2: Feature extraction (f0={F0_METHOD}) ---")
    run_applio(
        "run_extract_script",
        model_name=MODEL_NAME,
        f0_method=F0_METHOD,
        cpu_cores=CPU_CORES,
        gpu=GPU,
        sample_rate=SAMPLE_RATE,
        embedder_model=EMBEDDER,
        embedder_model_custom=None,
        include_mutes=2,
    )

    # ---- 3. Train ----
    print(f"\n--- Step 3: Train ({EPOCHS} epochs) ---")
    t_train = time.time()
    run_applio(
        "run_train_script",
        model_name=MODEL_NAME,
        save_every_epoch=10,
        save_only_latest=True,
        save_every_weights=False,
        total_epoch=EPOCHS,
        sample_rate=SAMPLE_RATE,
        batch_size=BATCH_SIZE,
        gpu=GPU,
        overtraining_detector=True,
        overtraining_threshold=50,
        pretrained=True,
        cleanup=False,
        index_algorithm="Auto",
        cache_data_in_gpu=False,
        custom_pretrained=False,
        vocoder="HiFi-GAN",
        checkpointing=False,
    )
    train_elapsed = time.time() - t_train
    print(f"Training took {train_elapsed/60:.1f} min")

    # ---- 4. Convert one line ----
    print("\n--- Step 4: Convert 00A_01_Narrator.wav ---")
    pth, index = find_trained_model()
    print(f"  Model: {pth.name}")
    print(f"  Index: {index.name if index else 'none'}")
    convert(pth, index)

    # ---- 5. Verify ----
    verify_duration()

    total = time.time() - t0
    print(f"\nTotal time: {total/60:.1f} min")
    print("Task 3: stop here and report. Do NOT batch-convert the 113 lines.")


if __name__ == "__main__":
    main()
