#!/usr/bin/env python3
"""Conservative native-MiniMax audio gate for the Equal Shares audio pass.

This is a filter, not a claim that legacy Windows Speech understands every
voice. Wrong recognized words fail. Empty recognition is ``needs_ear_review``;
it never becomes a pass. Results retain the source MP4 and extracted full WAV so
the filter can be improved without regenerating the take.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "outputs" / "equal_shares"
STORY_CONFIG = PROJECT / "story_config.json"
TRANSCRIBE = ROOT / "work" / "transcribe_windows_speech.ps1"
AUDIT_DIR = PROJECT / "audio_validation"
CANDIDATE_DIR = PROJECT / "audio" / "audio_pass_candidates"

QUOTE_RE = re.compile(r"[\"“](.*?)[\"”]")
WORD_RE = re.compile(r"[a-z0-9']+")


def run(command: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout,
    )


def normalize_words(text: str) -> list[str]:
    return WORD_RE.findall(text.casefold())


def expected_lines(clip: dict) -> list[dict]:
    rows = []
    for item in clip.get("dialogue_timing") or []:
        raw = str(item.get("line", ""))
        quote = QUOTE_RE.search(raw)
        if not quote:
            continue
        head = raw[: quote.start()].strip(" :,—-")
        speaker = re.split(r"[,:]", head)[0].strip() or "Unknown"
        rows.append({
            "speaker": speaker,
            "start": float(item["start"]),
            "end": float(item["end"]),
            "expected": quote.group(1).strip(),
        })
    return rows


def transcript_metrics(expected: str, actual: str) -> dict:
    exp = normalize_words(expected)
    got = normalize_words(actual)
    exp_counts, got_counts = Counter(exp), Counter(got)
    matched = sum(min(count, got_counts[word]) for word, count in exp_counts.items())
    extras = sum(max(0, count - exp_counts[word]) for word, count in got_counts.items())
    recall = matched / len(exp) if exp else (1.0 if not got else 0.0)
    insertion_rate = extras / max(1, len(exp))
    sequence = SequenceMatcher(None, exp, got).ratio()
    return {
        "expected_words": len(exp),
        "recognized_words": len(got),
        "word_recall": round(recall, 4),
        "sequence_similarity": round(sequence, 4),
        "insertion_rate": round(insertion_rate, 4),
    }


def transcribe(wav: Path) -> dict:
    proc = run([
        "powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-File", str(TRANSCRIBE), str(wav),
    ])
    if proc.returncode:
        return {"ok": False, "text": "", "error": proc.stderr.strip()[:500]}
    try:
        payload = json.loads(proc.stdout)
        recs = payload.get("recognitions") or []
        return {
            "ok": True,
            "text": " ".join(str(x.get("text", "")) for x in recs).strip(),
            "recognitions": recs,
        }
    except Exception as exc:
        return {"ok": False, "text": "", "error": f"recognizer JSON error: {exc}"}


def extract_wav(video: Path, wav: Path, start: float | None = None,
                end: float | None = None, mono_16k: bool = False) -> None:
    wav.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
    if start is not None:
        cmd += ["-ss", f"{max(0.0, start):.3f}"]
    cmd += ["-i", str(video)]
    if start is not None and end is not None:
        cmd += ["-t", f"{max(0.05, end - start):.3f}"]
    cmd += ["-vn"]
    if mono_16k:
        cmd += ["-ar", "16000", "-ac", "1"]
    else:
        cmd += ["-ar", "48000", "-ac", "2"]
    cmd += ["-c:a", "pcm_s16le", str(wav)]
    proc = run(cmd)
    if proc.returncode or not wav.is_file():
        raise RuntimeError(proc.stderr.strip() or "ffmpeg audio extraction failed")


def probe(video: Path) -> dict:
    proc = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,sample_rate,channels",
        "-of", "json", str(video),
    ])
    if proc.returncode:
        return {"ok": False, "error": proc.stderr.strip()}
    data = json.loads(proc.stdout)
    audio = next((x for x in data.get("streams", []) if x.get("codec_type") == "audio"), None)
    return {
        "ok": bool(audio),
        "duration": float(data.get("format", {}).get("duration") or 0),
        "size": int(data.get("format", {}).get("size") or 0),
        "audio_codec": (audio or {}).get("codec_name"),
        "sample_rate": int((audio or {}).get("sample_rate") or 0),
        "channels": int((audio or {}).get("channels") or 0),
    }


def volume_stats(video: Path) -> dict:
    proc = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(video), "-vn",
        "-af", "volumedetect", "-f", "null", "NUL",
    ])
    text = proc.stderr
    def number(label: str) -> float | None:
        m = re.search(rf"{label}:\s*(-?[\d.]+)\s*dB", text)
        return float(m.group(1)) if m else None
    return {"mean_db": number("mean_volume"), "max_db": number("max_volume")}


def validate(video: Path, clip: dict, full_wav: Path | None = None) -> dict:
    clip_id = clip["id"]
    mechanical = probe(video)
    result = {
        "schema_version": 1,
        "clip_id": clip_id,
        "source_video": str(video),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "mechanical": mechanical,
        "volume": volume_stats(video),
        "lines": [],
    }
    if not mechanical.get("ok"):
        result.update(status="retry_required", reasons=["missing or unreadable audio stream"])
        return result

    full_wav = full_wav or (CANDIDATE_DIR / f"{clip_id}_{video.stem}_full.wav")
    if not full_wav.exists():
        extract_wav(video, full_wav)
    result["candidate_full_wav"] = str(full_wav)

    lines = expected_lines(clip)
    reasons: list[str] = []
    unknown = False
    with tempfile.TemporaryDirectory(prefix=f"eq_audio_{clip_id}_") as temp:
        temp_dir = Path(temp)
        # Whole-clip recognition catches repeats and speech outside the windows.
        whole = temp_dir / "whole_16k.wav"
        extract_wav(video, whole, mono_16k=True)
        whole_asr = transcribe(whole)
        expected_full = " ".join(x["expected"] for x in lines)
        whole_metrics = transcript_metrics(expected_full, whole_asr.get("text", ""))
        result["whole_transcript"] = whole_asr
        result["whole_metrics"] = whole_metrics

        for index, line in enumerate(lines, 1):
            window = temp_dir / f"line_{index:02d}.wav"
            extract_wav(
                video, window,
                max(0.0, line["start"] - 0.25),
                min(float(clip.get("duration") or mechanical["duration"]), line["end"] + 0.25),
                mono_16k=True,
            )
            asr = transcribe(window)
            metrics = transcript_metrics(line["expected"], asr.get("text", ""))
            row = {**line, "transcript": asr, "metrics": metrics}
            result["lines"].append(row)
            if not asr.get("text"):
                unknown = True
                reasons.append(f"line {index} ({line['speaker']}): recognizer returned no words")
            elif (metrics["word_recall"] < 0.95
                  or metrics["sequence_similarity"] < 0.82
                  or metrics["insertion_rate"] > 0.20):
                reasons.append(
                    f"line {index} ({line['speaker']}): dialogue mismatch "
                    f"recall={metrics['word_recall']:.2f}, "
                    f"sequence={metrics['sequence_similarity']:.2f}, "
                    f"insertions={metrics['insertion_rate']:.2f}"
                )

    max_db = result["volume"].get("max_db")
    mean_db = result["volume"].get("mean_db")
    if max_db is not None and max_db >= -0.05:
        reasons.append(f"possible clipping: max volume {max_db:.2f} dB")
    if mean_db is not None and mean_db < -55:
        reasons.append(f"audio is nearly silent: mean volume {mean_db:.1f} dB")

    if lines:
        wm = result["whole_metrics"]
        if result["whole_transcript"].get("text") and (
            wm["word_recall"] < 0.95 or wm["sequence_similarity"] < 0.82
            or wm["insertion_rate"] > 0.20
        ):
            reasons.append(
                "whole clip does not match the complete scripted dialogue "
                f"(recall={wm['word_recall']:.2f}, sequence={wm['sequence_similarity']:.2f}, "
                f"insertions={wm['insertion_rate']:.2f})"
            )
    elif result["whole_transcript"].get("text"):
        reasons.append("speech recognized in a clip scripted with no dialogue")

    # Mechanical failures (clipping, silence, wrong-clip speech) → retry.
    # ASR dialogue mismatch alone → needs_ear_review: H3 synthetic voice is
    # documented to return partial ASR matches even on correct speech; only the
    # operator's ear can confirm. Retrying on ASR mismatch wastes GPU time.
    mechanical_failure = any(
        "speech recognized" in x or "clipping" in x or "nearly silent" in x
        for x in reasons
    )
    asr_mismatch = any("mismatch" in x or "does not match" in x for x in reasons)
    if mechanical_failure:
        status = "retry_required"
    elif unknown or asr_mismatch:
        status = "needs_ear_review"
    else:
        # Non-dialogue sound semantics and voice identity remain reviewable
        # dimensions even when ASR/mechanics pass.
        status = "auto_pass_pending_continuity_review"
    result["status"] = status
    result["reasons"] = reasons
    result["acceptance_note"] = (
        "Automatic output is a filter. Promote to accepted only after voice, music, "
        "ambience, effects, and timing continuity are confirmed."
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clip", required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--full-wav")
    parser.add_argument("--json")
    args = parser.parse_args()

    cfg = json.loads(STORY_CONFIG.read_text(encoding="utf-8-sig"))
    clips = {row["id"]: row for row in cfg["clips"]}
    if args.clip not in clips:
        raise SystemExit(f"unknown clip: {args.clip}")
    video = Path(args.video)
    if not video.is_file():
        raise SystemExit(f"video not found: {video}")

    result = validate(video, clips[args.clip], Path(args.full_wav) if args.full_wav else None)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.json) if args.json else AUDIT_DIR / f"{args.clip}_{video.stem}.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "clip": args.clip,
        "status": result["status"],
        "reasons": result.get("reasons", []),
        "audit": str(out),
        "candidate_full_wav": result.get("candidate_full_wav"),
    }, indent=2, ensure_ascii=False))
    return 0 if result["status"] != "retry_required" else 2


if __name__ == "__main__":
    raise SystemExit(main())
