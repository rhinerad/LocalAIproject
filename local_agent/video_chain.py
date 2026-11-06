#!/usr/bin/env python3
"""Clip-to-clip video continuity: last-frame extraction + ComfyUI input upload.

Used by batch_run_backrooms_gvd.py to chain the ACTUAL last rendered frame of
the previous clip into the next clip's MiniMaxH3ImageToVideo.first_frame,
instead of rendering a fresh FLUX still for every clip.

extract_last_frame() reuses the proven ffprobe-duration + single-frame ffmpeg
subprocess pattern from dspy_optimizer.extract_eval_frames() (same
CREATE_NO_WINDOW flag, same 15 s / 60 s timeouts, check=True), with two
deliberate differences because a wrong chain frame is silently wrong on
screen, whereas a wrong QA sample frame is merely a weaker QA sample:

  * failures RAISE ChainFrameError instead of falling back to a guessed
    duration -- the caller then renders a fresh still (the safe path);
  * the output name uses a CONTENT digest of the source video, not a path
    digest, so a re-rendered clip at the same path can never reuse a stale
    frame, and progress.json can prove which render a chain came from.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHAIN_FRAMES_DIR = HERE / "runtime" / "gvd_backrooms_batch" / "chain_frames"
# Decode window before end-of-stream; with -update 1 the final decoded frame
# wins, so this only needs to be comfortably longer than one frame (1/24 s)
# and tolerant of container-vs-stream duration mismatch.
LAST_FRAME_WINDOW_S = 1.0
MIN_FRAME_BYTES = 1024
VIDEO_SUFFIXES = frozenset({".mp4", ".webm", ".mov", ".mkv"})


class ChainFrameError(RuntimeError):
    """Last-frame extraction or upload failed; caller must fall back to a fresh still."""


def file_digest(path: Path, length: int = 10) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:length]


def _probe_duration(video_path: Path, flags: int) -> float:
    """Video-stream duration, falling back to container duration. Raises on failure."""
    for entries in ("stream=duration", "format=duration"):
        cmd = ["ffprobe", "-v", "error"]
        if entries.startswith("stream"):
            cmd += ["-select_streams", "v:0"]
        cmd += [
            "-show_entries",
            entries,
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        try:
            raw = subprocess.check_output(
                cmd, text=True, encoding="utf-8", timeout=15, creationflags=flags
            )
        except Exception as exc:
            raise ChainFrameError(f"ffprobe failed on {video_path}: {exc}") from exc
        for line in raw.splitlines():
            try:
                value = float(line.strip())
            except ValueError:
                continue  # "N/A" for streams without a duration tag
            if value > 0:
                return value
    raise ChainFrameError(f"ffprobe reported no usable duration for {video_path}")


def extract_last_frame(video_path: Path, out_dir: Path | None = None) -> Path:
    """Write the final decoded video frame of ``video_path`` as a PNG and return it.

    Output: ``<out_dir>/<stem>_<content-digest>_last.png`` (default out_dir is
    runtime/gvd_backrooms_batch/chain_frames/). Reuses an existing non-empty
    output for the same content digest.
    """
    video_path = Path(video_path)
    if not video_path.is_file():
        raise ChainFrameError(f"source video missing: {video_path}")
    if video_path.suffix.lower() not in VIDEO_SUFFIXES:
        raise ChainFrameError(f"source is not a video file: {video_path}")
    out = Path(out_dir) if out_dir is not None else CHAIN_FRAMES_DIR
    out.mkdir(parents=True, exist_ok=True)
    digest = file_digest(video_path)
    target = out / f"{video_path.stem}_{digest}_last.png"
    if target.is_file() and target.stat().st_size >= MIN_FRAME_BYTES:
        return target

    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    duration = _probe_duration(video_path, flags)
    sec = max(0.0, duration - LAST_FRAME_WINDOW_S)
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(video_path),
                "-ss",
                f"{sec:.3f}",
                # Overwrite the single output image with every decoded frame
                # so the file ends as the true last frame, independent of
                # duration rounding.
                "-update",
                "1",
                "-c:v",
                "png",
                "-y",
                str(target),
            ],
            check=True,
            capture_output=True,
            timeout=60,
            creationflags=flags,
        )
    except Exception as exc:
        raise ChainFrameError(f"ffmpeg last-frame extraction failed on {video_path}: {exc}") from exc
    if not target.is_file() or target.stat().st_size < MIN_FRAME_BYTES:
        raise ChainFrameError(f"ffmpeg produced no usable last frame for {video_path}")
    return target


def upload_to_comfy_input(png_path: Path, *, url: str, name: str | None = None) -> str:
    """POST a PNG to ComfyUI /upload/image (type=input); return the server-side name.

    Same multipart shape as gvd_qa/smoke_i2v_from_receipt.upload_input_png.
    bind_h3_image_frames() uses input-relative names verbatim, so the returned
    name is what must be passed on as start_frame_path.
    """
    png_path = Path(png_path)
    png = png_path.read_bytes()
    upload_name = name or png_path.name
    bound = uuid.uuid4().hex
    body = bytearray()

    def part(field: str, value: bytes, filename: str | None = None, ctype: str | None = None) -> None:
        body.extend(f"--{bound}\r\n".encode())
        disp = f'Content-Disposition: form-data; name="{field}"'
        if filename:
            disp += f'; filename="{filename}"'
        body.extend((disp + "\r\n").encode())
        if ctype:
            body.extend(f"Content-Type: {ctype}\r\n".encode())
        body.extend(b"\r\n")
        body.extend(value)
        body.extend(b"\r\n")

    part("image", png, upload_name, "image/png")
    part("overwrite", b"true")
    part("type", b"input")
    body.extend(f"--{bound}--\r\n".encode())
    req = urllib.request.Request(
        url.rstrip("/") + "/upload/image",
        data=bytes(body),
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={bound}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise ChainFrameError(f"ComfyUI upload of {png_path.name} failed: {exc}") from exc
    server_name = str((payload or {}).get("name") or "")
    subfolder = str((payload or {}).get("subfolder") or "")
    if not server_name:
        raise ChainFrameError(f"ComfyUI upload returned no name: {payload}")
    return f"{subfolder}/{server_name}" if subfolder else server_name
