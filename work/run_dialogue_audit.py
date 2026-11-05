"""Task 4: Transcribe selected takes and compute real dialogue accuracy numbers.

Reads manifest.json for selected clip paths, extracts audio via ffmpeg,
runs work/transcribe_windows_speech.ps1 on each, then compares the
transcription against the expected dialogue in story_config.json.

Writes outputs/equal_shares/dialogue_accuracy_audit.json with per-clip
word_recall and sequence_similarity numbers.

Runs on CPU — safe to run while GPU is rendering.
"""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
from difflib import SequenceMatcher
from pathlib import Path

ROOT   = Path(__file__).resolve().parents[1]
PROJ   = ROOT / "outputs" / "equal_shares"
CONFIG = PROJ / "story_config.json"
MANIF  = PROJ / "manifest.json"
PS1    = ROOT / "work" / "transcribe_windows_speech.ps1"
OUT    = PROJ / "dialogue_accuracy_audit.json"
FFMPEG = "ffmpeg"


def extract_expected(dialogue_timing: list[dict]) -> str:
    """Pull just the spoken words from dialogue_timing line entries."""
    parts = []
    for d in dialogue_timing:
        line = d.get("line", "")
        # Lines are: "Character, description: "quoted words"" or plain text.
        # Extract content inside double quotes first.
        quoted = re.findall(r'["“”‘’](.*?)["“”‘’]', line)
        if quoted:
            parts.extend(quoted)
        else:
            # Fall back to everything after the first colon.
            if ":" in line:
                parts.append(line.split(":", 1)[1].strip())
            else:
                parts.append(line.strip())
    return " ".join(parts)


def word_recall(expected: str, got: str) -> float:
    """Fraction of expected words found anywhere in the transcription."""
    if not expected:
        return 1.0
    exp_words = re.findall(r"\w+", expected.lower())
    got_words  = set(re.findall(r"\w+", got.lower()))
    if not exp_words:
        return 1.0
    return sum(1 for w in exp_words if w in got_words) / len(exp_words)


def seq_sim(expected: str, got: str) -> float:
    return SequenceMatcher(None,
                           re.sub(r"\W+", " ", expected.lower()).strip(),
                           re.sub(r"\W+", " ", got.lower()).strip()).ratio()


def extract_audio(video_path: Path, wav_path: Path) -> bool:
    result = subprocess.run(
        [FFMPEG, "-y", "-i", str(video_path),
         "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav_path)],
        capture_output=True,
    )
    return result.returncode == 0 and wav_path.exists()


def transcribe(wav_path: Path) -> str:
    result = subprocess.run(
        ["powershell", "-NonInteractive", "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(PS1), str(wav_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    if result.returncode != 0:
        return ""
    try:
        data = json.loads(result.stdout)
        parts = data.get("recognitions") or []
        return " ".join(p.get("text", "") for p in parts).strip()
    except Exception:
        return result.stdout.strip()


def main():
    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    manifest = json.loads(MANIF.read_text(encoding="utf-8-sig"))

    # Build dialogue_timing lookup by clip id
    dialogue_map: dict[str, list] = {}
    for clip in config.get("clips", []):
        dt = clip.get("dialogue_timing")
        if dt:
            dialogue_map[clip["id"]] = dt

    # Build clip-path lookup from manifest — use comfy_source (raw H3 render with audio)
    # Fall back to clip (assembled cut) if comfy_source absent or missing.
    clip_paths: dict[str, Path] = {}
    for cid, data in manifest.get("clips", {}).items():
        for field in ("comfy_source", "clip"):
            p = Path(data.get(field, ""))
            if p.exists():
                clip_paths[cid] = p
                break

    target_ids = sorted(set(dialogue_map) & set(clip_paths))
    print(f"Auditing {len(target_ids)} dialogue clips …", flush=True)

    # Load existing results to allow resume
    results: dict = {}
    if OUT.exists():
        try:
            results = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    with tempfile.TemporaryDirectory() as tmp:
        for i, cid in enumerate(target_ids):
            if cid in results and results[cid].get("transcription"):
                # Already done — skip
                print(f"  [{i+1}/{len(target_ids)}] {cid}: cached", flush=True)
                continue

            video = clip_paths[cid]
            wav   = Path(tmp) / f"{cid}.wav"

            if not extract_audio(video, wav):
                results[cid] = {"error": "ffmpeg failed", "word_recall": None, "seq_sim": None}
                print(f"  [{i+1}/{len(target_ids)}] {cid}: ffmpeg FAILED", flush=True)
                OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
                continue

            got = transcribe(wav)
            expected = extract_expected(dialogue_map[cid])

            wr = word_recall(expected, got)
            ss = seq_sim(expected, got)
            results[cid] = {
                "expected": expected,
                "transcription": got,
                "word_recall": round(wr, 3),
                "seq_sim": round(ss, 3),
                "pass": wr >= 0.7 and ss >= 0.5,
            }
            status = "PASS" if results[cid]["pass"] else "FAIL"
            print(f"  [{i+1}/{len(target_ids)}] {cid}: {status} "
                  f"recall={wr:.2f} sim={ss:.2f} | got: {got[:60]!r}", flush=True)

            # Write after each clip so we can resume
            OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Summary
    done = [v for v in results.values() if v.get("transcription") is not None]
    passed = [v for v in done if v.get("pass")]
    recalls = [v["word_recall"] for v in done if v.get("word_recall") is not None]
    sims    = [v["seq_sim"] for v in done if v.get("seq_sim") is not None]
    if recalls:
        import statistics
        print(f"\nDone {len(done)}/{len(target_ids)} clips")
        print(f"Pass rate: {len(passed)}/{len(done)} ({100*len(passed)/len(done):.0f}%)")
        print(f"Median word_recall: {statistics.median(recalls):.2f}")
        print(f"Median seq_sim:     {statistics.median(sims):.2f}")
    print(f"Results written to {OUT}", flush=True)


if __name__ == "__main__":
    main()
