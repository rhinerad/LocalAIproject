"""Build RVC training sets from H3 rendered clips.

For each trainable character, extracts every segment of their speech from all
rendered clips (using dialogue_timing windows from story_config.json), validates
each segment against the matching speech-recognition transcript, and concatenates
to:
    outputs/equal_shares/voices/<slug>/rvc_training/all_speech.wav

Filters applied
---------------
  * Source video missing from disk           → drop
  * Clip is a known-silent clip (room tone)  → drop
  * RMS of extracted segment < -55 dBFS      → drop (noise floor)
  * Speech-recognition overflow past window  → FLAG (kept, but noted)
  * Character total < 60 s after filtering   → SKIP, stays on Kokoro

Characters below the 60 s floor are noted at the end.

Usage
-----
    # Dry run: report per-character seconds, no audio touched
    python work/build_rvc_training_set.py --dry-run

    # Process all trainable characters
    python work/build_rvc_training_set.py --all

    # Process one character only
    python work/build_rvc_training_set.py --character narrator
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths — relative to project root (run this from COMFYUI_STORY_HANDOFF_2026-08-09)

PROJECT     = Path("outputs/equal_shares")
CONFIG      = PROJECT / "story_config.json"
MANIFEST    = PROJECT / "manifest.json"
VOICES      = PROJECT / "voices"
TRANSCRIPTS = PROJECT / "validation_transcripts"

# ---------------------------------------------------------------------------
# Constants

WINDOW_PAD   = 0.15    # seconds of padding on each side of the timing window
SILENCE_DBFS = -55.0   # mean_volume below this → drop (noise floor)
MIN_SECONDS  = 60.0    # characters below this after filtering stay on Kokoro

# Clips whose entire audio is known room tone (RVC would learn silence)
KNOWN_SILENT_CLIPS = {"04C", "06A", "14B", "14E", "16E", "17C"}

# Characters with < 60 s total in the film — stays on Kokoro, no RVC
NO_TRAIN = {
    "male visitor one", "male visitor two", "wealthy commuter",
    "unhoused man", "congregation member", "council member",
    "crew lead", "aid worker",
}

# Canonical slug map: lowercase speaker name → voice folder name
SLUG_MAP: dict[str, str] = {
    "narrator":               "narrator",
    "kent":                   "kent",
    "ryann sally":            "ryann_sally",
    "avery":                  "avery",
    "doris":                  "doris",
    "doris recording":        "doris",   # recording-over-phone, same voice model
    "faith white":            "faith_white",
    "volunteer":              "volunteer",
    "housing representative": "housing_representative",
}


# ---------------------------------------------------------------------------
# Helpers

def _read_json(path: str | Path) -> dict | list | None:
    p = Path(path)
    if not p.exists():
        return None
    with open(p, encoding="utf-8-sig") as fh:
        return json.load(fh)


def _norm(p: str) -> str:
    """Normalise Windows path separators."""
    return p.replace("\\", "/")


def speaker_of(line: str) -> str:
    """'Faith White, calm, looking at Kent: "..."' → 'Faith White'."""
    return line.split(":")[0].split(",")[0].strip()


def slug_of(name: str) -> str | None:
    return SLUG_MAP.get(name.lower())


def find_transcript(clip_id: str, comfy_source: str) -> dict | None:
    """Find the validation transcript that best matches the selected take.

    Priority:
      1. source_video basename matches comfy_source basename (exact take match)
      2. <clip>_known_attempt.json
      3. Highest-numbered <clip>_attempt_N.json
    """
    target_base = Path(_norm(comfy_source)).name
    all_t = list(TRANSCRIPTS.glob(f"{clip_id}_*.json"))

    for t_path in all_t:
        data = _read_json(t_path)
        if not data:
            continue
        sv = data.get("source_video", "")
        if Path(_norm(sv)).name == target_base:
            return data

    known = TRANSCRIPTS / f"{clip_id}_known_attempt.json"
    if known.exists():
        return _read_json(known)

    numbered = [t for t in all_t if "known" not in t.name]
    if numbered:
        def _n(p: Path) -> int:
            m = re.search(r"_attempt_(\d+)", p.name)
            return int(m.group(1)) if m else 0
        numbered.sort(key=_n, reverse=True)
        return _read_json(numbered[0])

    return None


def speech_overflow(transcript: dict, win_end: float, tol: float = 0.5) -> bool:
    """Return True if any recognition ends more than tol s past win_end."""
    for rec in transcript.get("recognitions", []):
        rec_end = rec.get("start", 0.0) + rec.get("duration", 0.0)
        if rec_end > win_end + tol:
            return True
    return False


def recs_in_window(transcript: dict, win_start: float, win_end: float) -> list:
    """Return recognitions that overlap the dialogue window."""
    return [
        r for r in transcript.get("recognitions", [])
        if r.get("start", 0.0) < win_end
        and r.get("start", 0.0) + r.get("duration", 0.0) > win_start
    ]


def measure_rms(wav_path: Path) -> float | None:
    """Return mean_volume dBFS for a WAV file, or None on error."""
    cmd = [
        "ffmpeg", "-v", "quiet",
        "-i", str(wav_path),
        "-af", "volumedetect",
        "-f", "null",
        os.devnull,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", r.stderr)
    return float(m.group(1)) if m else None


def extract_segment(
    video: str, pad_start: float, pad_dur: float, out: Path
) -> bool:
    """Extract audio window: mono 44.1 kHz with loudnorm. Returns True on success."""
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-ss", f"{pad_start:.4f}",
        "-t",  f"{pad_dur:.4f}",
        "-i", _norm(video),
        "-vn", "-ar", "44100", "-ac", "1",
        "-af", "loudnorm=I=-23:TP=-1.5:LRA=11",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"      [ffmpeg error] {r.stderr.strip()[:200]}")
    return r.returncode == 0


def wav_duration(path: Path) -> float | None:
    """Return duration in seconds via ffprobe, or None."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        return None


def concatenate(segment_files: list[Path], out: Path) -> bool:
    """Concatenate WAV files in order using ffmpeg concat demuxer."""
    list_path = out.parent / "_concat_list.txt"
    with open(list_path, "w", encoding="utf-8") as fh:
        for f in segment_files:
            fh.write(f"file '{f.resolve().as_posix()}'\n")
    cmd = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-ar", "44100", "-ac", "1",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    list_path.unlink(missing_ok=True)
    if r.returncode != 0:
        print(f"    [concat error] {r.stderr.strip()[:200]}")
    return r.returncode == 0


# ---------------------------------------------------------------------------
# Core

def collect_segments(
    target_slug: str | None = None,
) -> dict[str, list[dict]]:
    """Walk story_config + manifest and collect one dict per dialogue window."""
    config = _read_json(CONFIG)
    if not config:
        sys.exit(f"Cannot read {CONFIG}")
    manifest = _read_json(MANIFEST)
    if not manifest:
        sys.exit(f"Cannot read {MANIFEST}")

    m_clips: dict[str, dict] = manifest.get("clips", {})
    segments: dict[str, list[dict]] = defaultdict(list)
    unknown_speakers: set[str] = set()

    for clip in sorted(config["clips"], key=lambda c: c["sequence_order"]):
        clip_id = clip["id"]
        m = m_clips.get(clip_id)
        if not m:
            continue

        comfy_source = m.get("comfy_source", "")
        if not comfy_source:
            continue

        clip_dur = float(m.get("duration") or clip.get("duration") or 0)
        transcript = find_transcript(clip_id, comfy_source)

        for timing in clip.get("dialogue_timing") or []:
            name = speaker_of(timing["line"])
            slug = slug_of(name)

            if slug is None:
                key = name.lower()
                if key not in NO_TRAIN and key not in unknown_speakers:
                    unknown_speakers.add(key)
                    print(f"  [WARN] Unknown speaker '{name}' in {clip_id} — skipping")
                continue

            if target_slug and slug != target_slug:
                continue

            win_start = float(timing["start"])
            win_end   = float(timing["end"])
            pad_start = max(0.0, win_start - WINDOW_PAD)
            pad_end   = min(clip_dur, win_end + WINDOW_PAD)

            segments[slug].append({
                "clip_id":    clip_id,
                "speaker":    name,
                "win_start":  win_start,
                "win_end":    win_end,
                "duration":   win_end - win_start,
                "pad_start":  pad_start,
                "pad_dur":    pad_end - pad_start,
                "video":      _norm(comfy_source),
                "transcript": transcript,
            })

    return dict(segments)


def process_character(
    slug: str,
    segs: list[dict],
    dry_run: bool,
) -> tuple[float, float]:
    """Filter, extract, and concatenate for one character.

    Returns (raw_seconds, kept_seconds).
    """
    raw_seconds  = sum(s["duration"] for s in segs)
    kept_segs    = []
    dropped_secs = 0.0

    for seg in segs:
        clip_id = seg["clip_id"]
        drop_reason = None
        flags: list[str] = []

        # ---- clip-level checks (no disk access needed) ----
        if clip_id in KNOWN_SILENT_CLIPS:
            drop_reason = f"known-silent clip"

        elif not Path(seg["video"]).exists():
            drop_reason = f"source not found on disk"

        else:
            # ---- transcript-level checks ----
            t = seg["transcript"]
            if t:
                in_win = recs_in_window(t, seg["win_start"], seg["win_end"])
                if not in_win and t.get("recognized_words", 0) == 0:
                    drop_reason = "transcript: silence in window"
                if speech_overflow(t, seg["win_end"]):
                    flags.append("speech-overflow-past-window")

        if drop_reason:
            dropped_secs += seg["duration"]
            print(f"    DROP {clip_id:>4}: {drop_reason}")
            continue

        if flags:
            for f in flags:
                print(f"    FLAG {clip_id:>4}: {f}")

        kept_segs.append(seg)

    kept_raw_seconds = sum(s["duration"] for s in kept_segs)

    if dry_run or kept_raw_seconds < MIN_SECONDS:
        return raw_seconds, kept_raw_seconds

    # ---- extract segments ----
    rvc_dir = VOICES / slug / "rvc_training"
    seg_dir = rvc_dir / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)

    segment_files: list[Path] = []
    final_kept_seconds = 0.0

    for i, seg in enumerate(kept_segs):
        out = seg_dir / f"{seg['clip_id']}_{i:03d}.wav"

        ok = extract_segment(seg["video"], seg["pad_start"], seg["pad_dur"], out)
        if not ok:
            print(f"    [ERROR] extraction failed: {seg['clip_id']}")
            continue

        rms = measure_rms(out)
        if rms is not None and rms < SILENCE_DBFS:
            print(f"    DROP {seg['clip_id']:>4}: RMS={rms:.1f} dBFS (noise floor)")
            out.unlink(missing_ok=True)
            dropped_secs += seg["duration"]
            continue

        final_kept_seconds += seg["duration"]
        segment_files.append(out)

    if not segment_files:
        print(f"  -> {slug}: no segments survived extraction")
        return raw_seconds, 0.0

    # ---- concatenate ----
    out_wav = rvc_dir / "all_speech.wav"
    ok = concatenate(segment_files, out_wav)
    if ok:
        actual_dur = wav_duration(out_wav) or 0.0
        print(f"  -> {slug}: {out_wav}")
        print(f"     {len(segment_files)} segments, {actual_dur:.1f}s on disk")
    else:
        print(f"  -> {slug}: concatenation failed")

    return raw_seconds, final_kept_seconds


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--character", metavar="NAME",
                    help="Process one character only (slug or display name)")
    ap.add_argument("--all", action="store_true",
                    help="Process all trainable characters (default if no --character)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Report segments only; do not extract or write audio")
    args = ap.parse_args()

    target_slug: str | None = None
    if args.character:
        # Accept either slug ('narrator') or display name ('Narrator')
        target_slug = slug_of(args.character) or args.character.lower()

    print("=== RVC Training Set Builder ===")
    if args.dry_run:
        print("Dry run — no audio will be written.\n")

    segments = collect_segments(target_slug)

    if not segments:
        print("No segments found.")
        return

    # Header
    w = 25
    print(f"\n{'Character':<{w}} {'Windows':>7} {'Raw s':>7} {'Kept s':>8}  Status")
    print("-" * 60)

    summary_rows: list[dict] = []

    for slug in sorted(segments):
        segs = segments[slug]
        display = slug.replace("_", " ").title()
        print(f"\n{display}  ({len(segs)} windows)")

        raw_s, kept_s = process_character(slug, segs, dry_run=args.dry_run)

        if kept_s < MIN_SECONDS:
            status = f"SKIP — {kept_s:.1f}s < {MIN_SECONDS:.0f}s floor"
        elif args.dry_run:
            status = f"OK (dry run)"
        else:
            status = "OK — written"

        print(f"  {display:<{w-2}} {len(segs):>7} {raw_s:>7.1f} {kept_s:>8.1f}  {status}")
        summary_rows.append({
            "slug": slug, "display": display,
            "windows": len(segs), "raw_s": raw_s, "kept_s": kept_s,
            "status": status,
        })

    print("\n=== Summary ===")
    print(f"{'Character':<{w}} {'Windows':>7} {'Raw s':>7} {'Kept s':>8}  Status")
    print("-" * 60)
    for row in summary_rows:
        print(
            f"  {row['display']:<{w-2}} {row['windows']:>7}"
            f" {row['raw_s']:>7.1f} {row['kept_s']:>8.1f}  {row['status']}"
        )

    print("""
Characters staying on Kokoro (below 60 s floor — no RVC training):
  Male Visitor One, Male Visitor Two, Wealthy commuter, Unhoused man,
  Congregation member, Council member, Crew lead, Aid worker.
  Each has 2–6.5 s total across the 124 clips.
""")


if __name__ == "__main__":
    main()
