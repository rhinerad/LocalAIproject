"""Build OPENING_REVIEW_rvc.mp4 and OPENING_REVIEW_h3.mp4 from the 10 accepted opening clips.

Cut order: 1.mp4->2.mp4->3.mp4->4.mp4->5.mp4->6.mp4->8.mp4->7.mp4->9.mp4->10.mp4
Output:    1920x1080 H.264, 24fps
Score:     EQUAL_SHARES_CONTINUOUS_SCORE.wav at -25dB, sidechaincompress-ducked under dialogue
Run from project root:
    python work/build_review_cut.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
PROJ  = Path(__file__).resolve().parents[1]
VIDEO = Path("A:/Users/rhine/ComfyUI-Shared/output/video")
DLGD  = PROJ / "outputs/equal_shares/audio/dialogue"
SCORE = PROJ / "outputs/equal_shares/audio/EQUAL_SHARES_CONTINUOUS_SCORE.wav"
OUT   = PROJ / "outputs/equal_shares/review"
TMP   = OUT / "tmp"
TMP.mkdir(parents=True, exist_ok=True)

# Cut order: (video_filename, clip_id, dialogue_wav_stem, dialogue_start_s)
# 8.mp4 is an alt take of 00E; uses same Narrator line.
CUT = [
    ("1.mp4",  "00A",     "00A_01_Narrator_rvc",  1.0),
    ("2.mp4",  "00B",     "00B_01_Narrator_rvc",  1.0),
    ("3.mp4",  "00C",     "00C_01_Narrator_rvc",  0.5),
    ("4.mp4",  "00D",     "00D_01_Narrator_rvc",  1.0),
    ("5.mp4",  "00D2",    "00D2_01_Narrator_rvc", 1.0),
    ("6.mp4",  "00E",     "00E_01_Narrator_rvc",  0.5),
    ("8.mp4",  "00E_alt", "00E_01_Narrator_rvc",  0.5),
    ("7.mp4",  "00F",     "00F_01_Narrator_rvc",  1.0),
    ("9.mp4",  "00G",     "00G_01_Narrator_rvc",  1.0),
    ("10.mp4", "00I",     "00I_01_Narrator_rvc",  2.0),
]

W, H = 1920, 1080


# ---------------------------------------------------------------------------
# Helpers

def run(cmd: list[str], desc: str = "", check: bool = True) -> subprocess.CompletedProcess:
    print(f"  + {desc or cmd[0]}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        print(f"[ERROR] exit {r.returncode}")
        print(r.stderr[-2000:])
        sys.exit(1)
    return r


def probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return float(r.stdout.strip())


def probe_fps(path: Path) -> str:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    )
    return r.stdout.strip()   # e.g. "30/1" or "24/1"


# ---------------------------------------------------------------------------
# Step 1: Process each clip to a normalised intermediate (video only)

def process_clip_video(vfile: str, clip_id: str, idx: int) -> Path:
    src  = VIDEO / vfile
    dest = TMP / f"v_{idx:02d}_{clip_id}.mp4"
    if dest.exists():
        print(f"  [skip] {dest.name} already exists")
        return dest

    fps_str = probe_fps(src)
    # Need fps conform only if not 24fps
    fps_filter = ",fps=24" if fps_str != "24/1" else ""

    # scale to 1920x1080 lanczos, pad if aspect ratio doesn't match exactly
    vf = (
        f"scale={W}:{H}:flags=lanczos:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
        f"{fps_filter},"
        f"format=yuv420p"
    )

    run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-crf", "16", "-preset", "fast",
        str(dest),
    ], desc=f"video {vfile} -> {dest.name}")
    return dest


# ---------------------------------------------------------------------------
# Step 2: Concatenate video intermediates

def concat_video(intermediates: list[Path]) -> Path:
    out = TMP / "video_concat.mp4"
    if out.exists():
        print(f"  [skip] {out.name} already exists")
        return out

    list_f = TMP / "vconcat.txt"
    list_f.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in intermediates),
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_f),
        "-c:v", "copy",
        str(out),
    ], desc="concat video")
    return out


# ---------------------------------------------------------------------------
# Step 3: Build RVC dialogue audio track (single WAV for full cut duration)

def build_rvc_dialogue(cut_data: list[dict]) -> Path:
    out = TMP / "dialogue_rvc.wav"
    if out.exists():
        print(f"  [skip] {out.name} already exists")
        return out

    total_dur = cut_data[-1]["timeline_end"]
    n = len(cut_data)

    # One silence base + N delayed dialogue WAVs
    # adelay values in ms (integer, stereo left|right)
    filter_parts: list[str] = []
    input_args: list[str] = [
        "-f", "lavfi", "-t", f"{total_dur:.4f}",
        "-i", "anullsrc=r=48000:cl=stereo",
    ]

    for i, entry in enumerate(cut_data):
        wav = DLGD / f"{entry['dlg_stem']}.wav"
        input_args += ["-i", str(wav)]
        delay_ms = int((entry["timeline_start"] + entry["dlg_start"]) * 1000)
        filter_parts.append(
            f"[{i+1}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
            f"adelay={delay_ms}|{delay_ms}[d{i}]"
        )

    # amix all delayed streams with the silence base
    dlg_labels = "".join(f"[d{i}]" for i in range(n))
    mix_inputs = f"[0:a]{dlg_labels}amix=inputs={n+1}:normalize=0:duration=first[dlgout]"

    filter_complex = ";".join(filter_parts) + ";" + mix_inputs

    cmd = (
        ["ffmpeg", "-y"]
        + input_args
        + ["-filter_complex", filter_complex,
           "-map", "[dlgout]",
           "-ar", "48000", "-ac", "2",
           str(out)]
    )
    run(cmd, desc="build RVC dialogue track")
    return out


# ---------------------------------------------------------------------------
# Step 4: Build H3 audio track (concat native clip audio)

def build_h3_dialogue(cut_data: list[dict]) -> Path:
    out = TMP / "dialogue_h3.wav"
    if out.exists():
        print(f"  [skip] {out.name} already exists")
        return out

    # Extract audio from each clip, resample to 48kHz stereo
    segs: list[Path] = []
    for entry in cut_data:
        src  = VIDEO / entry["vfile"]
        dest = TMP / f"h3_{entry['cut_idx']:02d}_{entry['clip_id']}.wav"
        if not dest.exists():
            run([
                "ffmpeg", "-y", "-i", str(src),
                "-vn", "-ar", "48000", "-ac", "2",
                str(dest),
            ], desc=f"extract H3 audio {entry['vfile']}")
        segs.append(dest)

    list_f = TMP / "h3concat.txt"
    list_f.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in segs),
        encoding="utf-8",
    )
    run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(list_f),
        "-ar", "48000", "-ac", "2",
        str(out),
    ], desc="concat H3 audio")
    return out


# ---------------------------------------------------------------------------
# Step 5: Extract score segment

def extract_score(total_dur: float) -> Path:
    out = TMP / "score_segment.wav"
    if out.exists():
        print(f"  [skip] {out.name} already exists")
        return out

    run([
        "ffmpeg", "-y",
        "-i", str(SCORE),
        "-t", f"{total_dur:.4f}",
        "-ar", "48000", "-ac", "2",
        str(out),
    ], desc=f"extract score [{total_dur:.2f}s]")
    return out


# ---------------------------------------------------------------------------
# Step 6: Mix dialogue + score with sidechaincompress ducking

def mix_audio(dialogue: Path, score: Path, tag: str) -> Path:
    out = TMP / f"mix_{tag}.wav"
    if out.exists():
        print(f"  [skip] {out.name} already exists")
        return out

    # score at -25dB; sidechain-compressed -8dB under dialogue
    # threshold=0.02 (-34dBFS) catches speech onset
    # ratio=8 with makeup compensates to get ~-8dB reduction
    fc = (
        "[1:a]volume=-25dB[score_v];"
        "[score_v][0:a]sidechaincompress="
        "threshold=0.02:ratio=8:attack=50:release=1000:makeup=0dB[score_d];"
        "[0:a][score_d]amix=inputs=2:normalize=0:duration=longest[out]"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(dialogue),
        "-i", str(score),
        "-filter_complex", fc,
        "-map", "[out]",
        "-ar", "48000", "-ac", "2",
        str(out),
    ], desc=f"mix {tag} audio + score")
    return out


# ---------------------------------------------------------------------------
# Step 7: Mux video + audio

def mux(video: Path, audio: Path, out_name: str) -> Path:
    out = OUT / out_name
    run([
        "ffmpeg", "-y",
        "-i", str(video),
        "-i", str(audio),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        str(out),
    ], desc=f"mux -> {out_name}")
    return out


# ---------------------------------------------------------------------------
# Main

def main() -> None:
    print("=== Building Opening Review Cut ===\n")

    # Probe clip durations and build timeline
    print("Probing clip durations...")
    timeline_offset = 0.0
    cut_data: list[dict] = []
    for idx, (vfile, clip_id, dlg_stem, dlg_start) in enumerate(CUT):
        dur = probe_duration(VIDEO / vfile)
        entry = {
            "cut_idx":        idx,
            "vfile":          vfile,
            "clip_id":        clip_id,
            "dlg_stem":       dlg_stem,
            "dlg_start":      dlg_start,
            "duration":       dur,
            "timeline_start": timeline_offset,
            "timeline_end":   timeline_offset + dur,
        }
        cut_data.append(entry)
        print(f"  {vfile:8s}  {clip_id:8s}  {dur:.3f}s  tl={timeline_offset:.3f}-{timeline_offset+dur:.3f}")
        timeline_offset += dur

    total_dur = cut_data[-1]["timeline_end"]
    print(f"\nTotal cut duration: {total_dur:.3f}s ({total_dur/60:.2f}m)\n")

    # Step 1: process video
    print("--- Step 1: Process clip video ---")
    intermediates: list[Path] = []
    for entry in cut_data:
        p = process_clip_video(entry["vfile"], entry["clip_id"], entry["cut_idx"])
        intermediates.append(p)

    # Step 2: concat video
    print("\n--- Step 2: Concat video ---")
    video_track = concat_video(intermediates)

    # Step 3: RVC dialogue track
    print("\n--- Step 3: Build RVC dialogue track ---")
    rvc_dlg = build_rvc_dialogue(cut_data)

    # Step 4: H3 dialogue track
    print("\n--- Step 4: Build H3 dialogue track ---")
    h3_dlg = build_h3_dialogue(cut_data)

    # Step 5: score segment
    print("\n--- Step 5: Extract score ---")
    score_seg = extract_score(total_dur)

    # Step 6: mix audio
    print("\n--- Step 6: Mix audio ---")
    rvc_mix = mix_audio(rvc_dlg, score_seg, "rvc")
    h3_mix  = mix_audio(h3_dlg,  score_seg, "h3")

    # Step 7: mux
    print("\n--- Step 7: Mux final outputs ---")
    out_rvc = mux(video_track, rvc_mix, "OPENING_REVIEW_rvc.mp4")
    out_h3  = mux(video_track, h3_mix,  "OPENING_REVIEW_h3.mp4")

    # Duration check
    print("\n--- Duration check ---")
    rvc_dur = probe_duration(out_rvc)
    h3_dur  = probe_duration(out_h3)
    print(f"  RVC: {rvc_dur:.3f}s  H3: {h3_dur:.3f}s  expected: {total_dur:.3f}s")

    # Write manifest
    manifest = {
        "total_duration_s": total_dur,
        "output_resolution": f"{W}x{H}",
        "fps": 24,
        "clips": [
            {
                "cut_position": e["cut_idx"] + 1,
                "source": e["vfile"],
                "clip_id": e["clip_id"],
                "duration_s": e["duration"],
                "timeline_start_s": e["timeline_start"],
                "timeline_end_s": e["timeline_end"],
                "rvc_wav": e["dlg_stem"] + ".wav",
                "dialogue_offset_in_clip_s": e["dlg_start"],
            }
            for e in cut_data
        ],
        "outputs": {
            "rvc": str(out_rvc),
            "h3":  str(out_h3),
        },
    }
    manifest_path = OUT / "OPENING_REVIEW_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest: {manifest_path}")
    print(f"RVC:      {out_rvc}")
    print(f"H3:       {out_h3}")
    print("\nDone.")


if __name__ == "__main__":
    main()
