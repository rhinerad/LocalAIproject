"""Stitch numbered PNG frames into an H.264 mp4."""
from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG = Path(
    r"A:\Users\rhine\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1-full_build\bin\ffmpeg.exe"
)


def assemble_png_sequence(
    frame_dir: Path,
    pattern: str,
    dest: Path,
    *,
    fps: int = 6,
    ffmpeg: Path | None = None,
) -> Path:
    exe = Path(ffmpeg) if ffmpeg is not None else FFMPEG
    if not exe.is_file():
        raise FileNotFoundError(f"ffmpeg missing: {exe}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(exe), "-y",
        "-framerate", str(fps),
        "-i", str(Path(frame_dir) / pattern),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(dest),
    ]
    subprocess.check_call(cmd)
    if not dest.is_file() or dest.stat().st_size < 1:
        raise RuntimeError(f"ffmpeg wrote no video: {dest}")
    return dest
