#!/usr/bin/env python3
"""Deterministic camera-motion estimate from decoded frames. No VLM.

Why: the action-log VLM writes ``cam=static`` for every frame of every clip,
drone and handheld included (CHANGELOG 2026-09-25b). This module measures it
instead. Every frame is decoded small and grey; for each consecutive pair a
3x3 grid of block-wise phase correlations gives one translation per block,
and a similarity fit (translation + isotropic scale about the frame centre)
turns the nine block shifts into a global pan/tilt and a zoom. Per-pair
values are summed over each observation window and classified into the
same vocabulary the action log's ``cam=`` slot uses:

    static | push-in | pull-back | pan-left | pan-right | tilt-up | tilt-down | uncertain

Sign convention (pinned by test_camera_motion.py): ``dx > 0`` means picture
content moved right between the two frames, i.e. the camera panned LEFT;
``dy > 0`` means content moved down, i.e. the camera tilted UP; ``scale > 0``
means content moved outward from the centre, i.e. push-in.

Border ring and coherence (2026-09-25e): the fit uses only the outer ring
of a 4x4 grid (12 blocks), on the assumption that the subject sits nearer
the centre and the background at the edges; the centre blocks are compared
against the fitted model and their excess motion is reported as
``subject_motion``. Each pair also gets a ``coherence`` score: the weighted
fraction of border blocks whose measured shift lies within tolerance of the
fitted translation+scale. It is reported, not used to relabel: measured on
the labeled clips, a drone tracking shot over a 3D scene is *incoherent*
(parallax: near and far blocks shift by different amounts) while a creek
filling the frame is perfectly *coherent* (uniform flow), so coherence does
not separate camera from subject. See CHANGELOG 2026-09-25e.

Limits, stated plainly: this is global image motion, not camera motion. A
dolly and a zoom both read as scale; rotation is not modelled and degrades
the fit; a moving subject that reaches the border ring (water filling the
frame, wings spanning the picture) still reads as a camera move. Low
phase-correlation response (cut, black frame, pure flicker, flat picture)
yields ``uncertain`` rather than a guess.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import numpy as np

W, H = 256, 144
GRID = 4
# Coherence: a border block agrees with the fit when its shift is within
# COHERENCE_TOL_PX plus COHERENCE_TOL_FRAC of the predicted shift magnitude.
COHERENCE_TOL_PX = 1.0
COHERENCE_TOL_FRAC = 0.25
# Coherence is diagnostic only (see the module docstring); no threshold gates on it.
# Mean excess motion of the centre blocks over the border fit, per pair, that
# counts as a moving subject in front of a steady background.
SUBJECT_EXCESS_PX = 1.0
# Per-window classification thresholds (fractions of frame width/height, and
# summed scale). Below both: static.
STATIC_FRAC = 0.02
ZOOM_MIN = 0.02
# Phase-correlation peak below this on a pair: no usable estimate for the pair.
MIN_RESPONSE = 0.10   # real footage: adjacent frames 0.14-0.64 (fast motion at the low end), across a cut 0.06-0.09
# Frames darker than this mean luma are blank (same value as video_judge).
BLACK_LUMA = 16.0
# Ignore block shifts larger than this fraction of the block size (wrap-around
# and aliasing make them unreliable).
MAX_SHIFT_FRAC = 0.25
CAMERA_VALUES = ("static", "push-in", "pull-back", "pan-left", "pan-right",
                 "tilt-up", "tilt-down", "uncertain")


# ---------------------------------------------------------------- decoding

def decode_gray(video: Path, width: int = W, height: int = H) -> np.ndarray:
    """Every frame of ``video`` as float32 grey (N, height, width)."""
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={width}:{height}",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        capture_output=True, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout
    if not raw:
        raise ValueError(f"ffmpeg decoded no frames from {video}")
    return np.frombuffer(raw, np.uint8).reshape(-1, height, width).astype(np.float32)


def video_fps(video: Path, default: float = 24.0) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout.strip()
    try:
        num, den = out.split("/")
        fps = float(num) / float(den)
        return fps if fps > 0 else default
    except Exception:
        return default


# ---------------------------------------------------------------- phase correlation

def _hann2d(h: int, w: int) -> np.ndarray:
    return np.outer(np.hanning(h), np.hanning(w)).astype(np.float32)


def phase_shift(a: np.ndarray, b: np.ndarray) -> tuple[float, float, float]:
    """Translation (dx, dy) that maps ``a`` onto ``b``, plus peak response.

    ``b(x) ≈ a(x - d)`` gives ``d``; a picture that slid right returns dx > 0.
    Sub-pixel by parabolic fit around the peak. Response is the normalised
    cross-power peak: ~1 for a pure shift, ~0.03 for unrelated pictures.
    """
    h, w = a.shape
    win = _hann2d(h, w)
    fa = np.fft.fft2((a - a.mean()) * win)
    fb = np.fft.fft2((b - b.mean()) * win)
    cross = fa * np.conj(fb)
    cross /= np.abs(cross) + 1e-9
    corr = np.real(np.fft.ifft2(cross))
    peak = int(np.argmax(corr))
    py, px = divmod(peak, w)
    response = float(corr[py, px])

    def _sub(prev: float, cur: float, nxt: float) -> float:
        den = prev - 2.0 * cur + nxt
        return 0.0 if abs(den) < 1e-12 else float(0.5 * (prev - nxt) / den)

    sx = _sub(corr[py, (px - 1) % w], corr[py, px], corr[py, (px + 1) % w])
    sy = _sub(corr[(py - 1) % h, px], corr[py, px], corr[(py + 1) % h, px])
    # the peak of a * conj(b) sits at -d; wrap to signed and flip the sign
    dx = -(px + sx if px + sx <= w / 2 else px + sx - w)
    dy = -(py + sy if py + sy <= h / 2 else py + sy - h)
    return float(dx), float(dy), response


def _fit_similarity(c: np.ndarray, v: np.ndarray, wts: np.ndarray) -> tuple[np.ndarray, float]:
    """Weighted least squares of v_i = t + s * c_i (translation + isotropic scale)."""
    wn = wts / wts.sum()
    t = (v * wn[:, None]).sum(0)
    cm = (c * wn[:, None]).sum(0)
    cc = c - cm
    denom = float((wn * (cc ** 2).sum(1)).sum())
    s = float((wn * ((v - t) * cc).sum(1)).sum() / denom) if denom > 0 else 0.0
    # with a non-centred block set the translation is taken at the frame centre
    t = t - s * cm
    return t, s


_ZERO = {"dx": 0.0, "dy": 0.0, "scale": 0.0, "response": 0.0, "coherence": 0.0,
         "subject_excess_px": 0.0, "full_dx": 0.0, "full_dy": 0.0, "full_scale": 0.0}


def pair_motion(a: np.ndarray, b: np.ndarray, grid: int = GRID) -> dict[str, float]:
    """Camera translation and scale between two grey frames, from the border ring.

    Block shifts v_i at block centres c_i (relative to the frame centre) on a
    ``grid`` x ``grid`` lattice. The outer ring is fitted to v_i = t + s * c_i
    (``t`` pixels, ``s`` scale change per pair) and gives ``dx``, ``dy``,
    ``scale``. ``coherence`` is the weighted fraction of ring blocks within
    tolerance of that fit; ``subject_excess_px`` the mean excess motion of
    the centre blocks over the fit; ``full_*`` the all-blocks fit for
    reference.
    """
    h, w = a.shape
    if float(a.mean()) < BLACK_LUMA or float(b.mean()) < BLACK_LUMA:
        return {**_ZERO, "blank": True}
    bh, bw = h // grid, w // grid
    centres, shifts, weights, border = [], [], [], []
    for gy in range(grid):
        for gx in range(grid):
            ys, xs = slice(gy * bh, (gy + 1) * bh), slice(gx * bw, (gx + 1) * bw)
            dx, dy, resp = phase_shift(a[ys, xs], b[ys, xs])
            if abs(dx) > MAX_SHIFT_FRAC * bw or abs(dy) > MAX_SHIFT_FRAC * bh:
                resp = 0.0
            centres.append(((gx + 0.5) * bw - w / 2.0, (gy + 0.5) * bh - h / 2.0))
            shifts.append((dx, dy))
            weights.append(max(resp, 0.0))
            border.append(gy in (0, grid - 1) or gx in (0, grid - 1))
    c = np.array(centres, dtype=np.float64)
    v = np.array(shifts, dtype=np.float64)
    wts = np.array(weights, dtype=np.float64)
    ring = np.array(border, dtype=bool)
    if wts[ring].sum() <= 1e-9:
        return {**_ZERO, "blank": False}
    t, s = _fit_similarity(c[ring], v[ring], wts[ring])
    pred = t + s * c
    err = np.linalg.norm(v - pred, axis=1)
    tol = COHERENCE_TOL_PX + COHERENCE_TOL_FRAC * np.linalg.norm(pred, axis=1)
    wr = wts[ring] / wts[ring].sum()
    coherence = float((wr * (err[ring] <= tol[ring])).sum())
    inner = ~ring
    if inner.any() and wts[inner].sum() > 1e-9:
        wi = wts[inner] / wts[inner].sum()
        subject_excess = float((wi * err[inner]).sum())
    else:
        subject_excess = 0.0
    if wts.sum() > 1e-9:
        tf, sf = _fit_similarity(c, v, wts)
    else:
        tf, sf = t, s
    return {"dx": float(t[0]), "dy": float(t[1]), "scale": s,
            "response": float(np.average(wts[ring])), "coherence": coherence,
            "subject_excess_px": subject_excess,
            "full_dx": float(tf[0]), "full_dy": float(tf[1]), "full_scale": float(sf),
            "blank": False}


def estimate_pairs(frames: np.ndarray) -> list[dict[str, float]]:
    """pair_motion for every consecutive frame pair of (N, H, W) grey frames."""
    return [pair_motion(frames[i], frames[i + 1]) for i in range(int(frames.shape[0]) - 1)]


# ---------------------------------------------------------------- classification

def classify(dx_frac: float, dy_frac: float, scale: float, response: float) -> str:
    """Window label from summed motion (fractions of frame size) and mean response."""
    if response < MIN_RESPONSE:
        return "uncertain"
    ratios = {"pan": abs(dx_frac) / STATIC_FRAC, "tilt": abs(dy_frac) / STATIC_FRAC,
              "zoom": abs(scale) / ZOOM_MIN}
    kind = max(ratios, key=ratios.get)
    if ratios[kind] < 1.0:
        return "static"
    if kind == "pan":
        return "pan-left" if dx_frac > 0 else "pan-right"
    if kind == "tilt":
        return "tilt-up" if dy_frac > 0 else "tilt-down"
    return "push-in" if scale > 0 else "pull-back"


def summarize_pairs(pairs: list[dict[str, float]], width: int = W, height: int = H) -> dict[str, Any]:
    """Sum a window's pairs; pairs without a usable response are excluded and counted.

    Adds ``coherence`` (mean over usable pairs, diagnostic), ``subject_motion``
    (centre blocks moving over a steadier border) and the all-blocks label
    ``full_frame_camera`` for comparison.
    """
    usable = [p for p in pairs if p["response"] >= MIN_RESPONSE]
    low = len(pairs) - len(usable)
    dx = sum(p["dx"] for p in usable)
    dy = sum(p["dy"] for p in usable)
    sc = sum(p["scale"] for p in usable)
    fdx = sum(p.get("full_dx", p["dx"]) for p in usable)
    fdy = sum(p.get("full_dy", p["dy"]) for p in usable)
    fsc = sum(p.get("full_scale", p["scale"]) for p in usable)
    response = float(np.mean([p["response"] for p in pairs])) if pairs else 0.0
    coherence = float(np.mean([p.get("coherence", 1.0) for p in usable])) if usable else 0.0
    excess = float(np.mean([p.get("subject_excess_px", 0.0) for p in usable])) if usable else 0.0
    out = {"pairs": len(pairs), "low_response_pairs": low,
           "dx_frac": round(dx / width, 4), "dy_frac": round(dy / height, 4),
           "scale": round(sc, 4), "response": round(response, 3),
           "coherence": round(coherence, 3), "subject_excess_px": round(excess, 2),
           "subject_motion": bool(usable) and excess >= SUBJECT_EXCESS_PX}
    if not pairs or low > len(pairs) / 2:
        out["camera"] = "uncertain"
        out["full_frame_camera"] = "uncertain"
        return out
    out["camera"] = classify(out["dx_frac"], out["dy_frac"], out["scale"], response)
    out["full_frame_camera"] = classify(round(fdx / width, 4), round(fdy / height, 4), round(fsc, 4), response)
    return out


def estimate_from_frames(frames: np.ndarray, fps: float, windows: list[dict]) -> list[dict[str, Any]]:
    """One summary per observation window ({frame, start, end}) from decoded frames.

    A pair (i -> i+1) belongs to the window that contains the time of frame
    i+1, ``(i + 1) / fps``, as ``start < t <= end``.
    """
    pairs = estimate_pairs(frames)
    height, width = int(frames.shape[1]), int(frames.shape[2])
    out = []
    for win in windows:
        start, end = float(win["start"]), float(win["end"])
        mine = [p for i, p in enumerate(pairs) if start < (i + 1) / fps <= end]
        summary = summarize_pairs(mine, width, height)
        out.append({"frame": win["frame"], "start": start, "end": end, **summary})
    return out


def estimate_camera_motion(video: Path, windows: list[dict], fps: float | None = None) -> list[dict[str, Any]]:
    """Decode ``video`` and estimate camera motion for each observation window."""
    frames = decode_gray(Path(video))
    return estimate_from_frames(frames, fps or video_fps(Path(video)), windows)


def compare_with_claims(estimates: list[dict[str, Any]], claims: dict[str, str]) -> dict[str, Any]:
    """Model ``cam=`` claims (frame -> value, from _action_coverage) vs estimates."""
    agree, disagree = [], []
    for est in estimates:
        claim = claims.get(str(est["frame"]))
        if claim is None or est["camera"] == "uncertain":
            continue
        (agree if claim == est["camera"] else disagree).append(
            {"frame": est["frame"], "claimed": claim, "measured": est["camera"]})
    return {"agree": len(agree), "disagree": disagree,
            "measured_values": {str(e["frame"]): e["camera"] for e in estimates}}
