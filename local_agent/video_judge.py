"""Fault-checked video judge for the Generalized Video Director live metric.

Why this exists (CHANGELOG 2026-09-24, judge entry): the holistic judge let the
VLM write three numbers before any reasoning and compared the clip with the
student's own prompts. Scores collapsed to two default triples, and clips with
no requested subject, hard cuts, location drift or text logos passed.

This module keeps the three-axis schema `parse_video_director_scores` and
MIPRO expect, and adds:

* a CPU hard-cut / blank-frame detector over every decoded frame (no VLM);
* a VLM prompt that is judged against the BRIEF (user intent + constraints),
  describes every frame before answering explicit yes/no fault checks, and
  only then scores;
* Python caps: a failed check bounds the relevant axis, whatever number the
  VLM wrote.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import numpy as np

AXES = ("text_video_alignment", "temporal_consistency", "aesthetic_quality")

# ------------------------------------------------------------------ CPU checks

_W, _H = 64, 36
# Calibrated on the 50-clip labeled set (runtime/dspy_opt/judge_eval/): these
# flag 4 of 10 labeled hard cuts and none of the good/partial clips. Gradual
# (morph) cuts are left to the VLM checks.
CUT_MIN_STEP = 0.20      # colour-histogram distance between consecutive frames (0..1)
CUT_MIN_RATIO = 8.0      # step / median of the surrounding +-12 steps
CUT_MAX_CORR = 0.70      # grayscale layout correlation across the step
CUT_SKIP_FRAMES = 2      # MiniMax I2V pops from the conditioning still on 0->1, 1->2
CUT_RETURN_FRAMES = 12   # look this far ahead for the pre-step picture coming back
CUT_RETURN_FRACTION = 0.5
BLANK_MEAN_LUMA = 16.0   # a frame whose mean luma (0-255) is below this is near-black
# A step into/out of a near-black frame is not a cut (c017 lights-off flicker:
# dark side 14.7). Narrow margin: M03's real cut lands on a 17.2 frame.
CUT_MIN_SIDE_LUMA = BLANK_MEAN_LUMA
BLANK_MIN_FRACTION = 0.25
# A lighting dip (c018: lights out 1.0 s, back dim at ~20 luma, then ~80 luma
# at 1.83 s) ends with a step whose dark side is not near-black and whose
# histogram never returns, so the flash rules above miss it. The picture on
# the lit side of such a step matches the picture on the far side of the dip:
# grayscale layout correlation 0.82-0.91 on c018 vs <= 0.56 across every
# labeled real cut. Frames at least CUT_DIP_FRACTION times darker than the lit
# side, for up to CUT_DIP_MAX_FRAMES, are the dip; the first lit frame beyond
# it is compared with the lit side at CUT_MAX_CORR.
CUT_DIP_FRACTION = 0.5
CUT_DIP_MAX_FRAMES = 48
# A sampled frame in a lighting dip carries no scene evidence (c004: F2 at
# 1.59 s has mean luma 2; the VLM called it "a different dark hallway"). The
# user prompt marks sampled frames that fall in a near-black run, or in a run
# dimmer than DIM_FRACTION x the median lit luma, so the VLM judges place and
# cuts from the lit frames.
DIM_FRACTION = 0.5
# A requested camera turn read as a cut (c038, held-out good: the walk turns
# to face the wall; the VLM called F4-F8 "close-up of wallpaper, no hallway",
# cut "yes", same place "no"). The camera-motion estimator (camera_motion.py,
# 2026-09-25c/e, consumed unchanged) is run over the gaps between consecutive
# sampled frames and a gap that is a rigid pan or tilt is marked in the user
# prompt the way dark_spans_s marks a lighting dip. Two gates on the
# estimator's own output, chosen from its readings on all 87 labeled clips
# before the VLM saw any mark (judge_eval_20260925/camera_gaps_v3e.txt): the
# picture must have slid by at least TURN_MIN_FRAC of the frame across the
# gap (the 25c creek confounder, water flowing down the frame, reads tilt-up
# at 0.13-0.15 per gap; c038's turn reads 0.46 and 0.32), and the estimator's
# subject_motion flag must be off (the centre moved with the border: a rigid
# turn, not a moving subject, a morph or a drift; c030's and D01 086a's
# swings all carry the flag).
TURN_MIN_FRAC = 0.20
TURN_LABELS = {"pan-left": "turned left", "pan-right": "turned right",
               "tilt-up": "tilted up", "tilt-down": "tilted down"}


def _decode_small(video: Path) -> np.ndarray:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"scale={_W}:{_H}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True, timeout=120,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    ).stdout
    if not raw:
        raise ValueError(f"ffmpeg decoded no frames from {video}")
    return np.frombuffer(raw, np.uint8).reshape(-1, _H, _W, 3).astype(np.float32)


def _hist(frame: np.ndarray) -> np.ndarray:
    return np.concatenate([
        np.histogram(frame[..., c], bins=16, range=(0, 256))[0] for c in range(3)
    ]) / float(_W * _H)


def _layout_corr(a: np.ndarray, b: np.ndarray) -> float:
    a, b = a - a.mean(), b - b.mean()
    return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))


def _dip_returns_same_picture(gray: np.ndarray, luma: np.ndarray, t: int) -> bool:
    """Step t -> t+1 is one edge of a lighting dip on an unchanged picture.

    The lit side is the brighter of the two frames. Walking away from the step
    on the dark side, frames darker than CUT_DIP_FRACTION x the lit luma are
    the dip (at most CUT_DIP_MAX_FRAMES); the first frame beyond it is the far
    reference. True when the lit frame and the far reference share their
    layout (correlation >= CUT_MAX_CORR). With no dip (both sides similarly
    lit) the reference is the adjacent frame, whose correlation already failed
    the CUT_MAX_CORR test, so this never rescues a plain cut.
    """
    n = len(luma)
    if luma[t + 1] > luma[t]:
        lit, j, step_dir = t + 1, t, -1
    else:
        lit, j, step_dir = t, t + 1, 1
    walked = 0
    while 0 <= j < n and walked < CUT_DIP_MAX_FRAMES and luma[j] < CUT_DIP_FRACTION * luma[lit]:
        j += step_dir
        walked += 1
    if walked == 0 or not (0 <= j < n) or walked >= CUT_DIP_MAX_FRAMES:
        return False
    return _layout_corr(gray[lit], gray[j]) >= CUT_MAX_CORR


def frame_signals(frames: np.ndarray, fps: float = 24.0) -> dict[str, Any]:
    """Hard cuts and blank frames from decoded RGB frames (N, H, W, 3)."""
    n = int(frames.shape[0])
    gray = frames.mean(-1)
    hists = np.array([_hist(f) for f in frames])
    steps = np.abs(np.diff(hists, axis=0)).sum(1) / 6.0 if n > 1 else np.zeros(0)
    luma = gray.reshape(n, -1).mean(1) if n else np.zeros(0)
    cuts: list[float] = []
    for t in range(CUT_SKIP_FRAMES, len(steps)):
        if steps[t] < CUT_MIN_STEP:
            continue
        lo, hi = max(0, t - 12), min(len(steps), t + 13)
        neighbours = np.concatenate([steps[lo:t], steps[t + 1:hi]])
        ratio = steps[t] / (float(np.median(neighbours)) + 0.005) if len(neighbours) else 0.0
        if ratio < CUT_MIN_RATIO:
            continue
        a, b = gray[t] - gray[t].mean(), gray[t + 1] - gray[t + 1].mean()
        corr = float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-6))
        if corr >= CUT_MAX_CORR:
            continue
        # Lights going off/on (dark side of the step) is exposure, not a new
        # shot; near-black frames are scored by blank_fraction instead.
        if min(gray[t].mean(), gray[t + 1].mean()) < CUT_MIN_SIDE_LUMA:
            continue
        # A flicker or flash comes back to the earlier picture; a cut does not.
        # Forward: the pre-step picture reappears. Backward: the post-step
        # picture was already on screen just before (the step out of a flash).
        limit = CUT_RETURN_FRACTION * steps[t]
        later = hists[t + 2:t + 2 + CUT_RETURN_FRAMES]
        if len(later) and float(np.abs(later - hists[t]).sum(1).min() / 6.0) < limit:
            continue
        earlier = hists[max(0, t - CUT_RETURN_FRAMES):t]
        if len(earlier) and float(np.abs(earlier - hists[t + 1]).sum(1).min() / 6.0) < limit:
            continue
        # The end (or start) of a lighting dip: the same picture, lit, is on
        # the far side of the dark stretch. Exposure-invariant (layout
        # correlation), so a dim-but-not-black stretch counts too.
        if _dip_returns_same_picture(gray, luma, t):
            continue
        cuts.append(round((t + 1) / fps, 2))
    blank = float(np.mean(luma < BLANK_MEAN_LUMA)) if n else 0.0
    return {"frames": n, "hard_cuts_s": cuts, "blank_fraction": round(blank, 3),
            "dark_spans_s": dark_spans(luma, fps)}


def dark_spans(luma: np.ndarray, fps: float) -> list[list]:
    """[[start_s, end_s, kind], ...] for runs of near-black frames (mean luma
    below BLANK_MEAN_LUMA) and of dim frames (below DIM_FRACTION x the median
    luma of the lit frames). end_s is the time of the last frame in the run.
    Used to tell the VLM which sampled frames carry no scene evidence."""
    n = len(luma)
    if n == 0:
        return []
    lit = luma[luma >= BLANK_MEAN_LUMA]
    dim_below = DIM_FRACTION * float(np.median(lit)) if len(lit) else 0.0
    kinds = ["near-black" if v < BLANK_MEAN_LUMA else ("dim" if v < dim_below else "") for v in luma]
    spans: list[list] = []
    start = 0
    for i in range(1, n + 1):
        if i == n or kinds[i] != kinds[start]:
            if kinds[start]:
                spans.append([round((start + 1) / fps, 2), round(i / fps, 2), kinds[start]])
            start = i
    return spans


def measured_camera_moves(video: Path, frame_times: list[float] | None) -> list[dict]:
    """Camera motion over each gap between consecutive sampled frames, from
    camera_motion.estimate_camera_motion (2026-09-25c/e). One record per gap,
    keyed by the 1-based index of the later frame. Empty with fewer than two
    frame times. Decodes the clip once more (grey, 256x144), about a second."""
    times = [float(t) for t in (frame_times or [])]
    if len(times) < 2:
        return []
    import camera_motion

    windows = [{"frame": i + 2, "start": a, "end": b} for i, (a, b) in enumerate(zip(times, times[1:]))]
    keep = ("frame", "start", "end", "camera", "dx_frac", "dy_frac", "scale", "response",
            "pairs", "low_response_pairs", "subject_motion")
    return [{k: est.get(k) for k in keep} for est in camera_motion.estimate_camera_motion(Path(video), windows)]


def turn_amount(move: dict) -> float:
    """How far the picture slid on the turn axis across the gap, as a fraction
    of the frame; 0 for a gap the estimator did not call a pan or tilt."""
    camera = str(move.get("camera") or "")
    if camera in ("pan-left", "pan-right"):
        return abs(float(move.get("dx_frac") or 0.0))
    if camera in ("tilt-up", "tilt-down"):
        return abs(float(move.get("dy_frac") or 0.0))
    return 0.0


def measured_turns(moves: list | None) -> dict[int, str]:
    """Later-frame index -> "turned left" etc. for each gap that is a rigid
    camera turn: a pan or tilt of at least TURN_MIN_FRAC without the
    estimator's subject_motion flag."""
    turns: dict[int, str] = {}
    for move in moves or []:
        camera = str(move.get("camera") or "")
        if camera in TURN_LABELS and turn_amount(move) >= TURN_MIN_FRAC and not move.get("subject_motion"):
            turns[int(move["frame"])] = TURN_LABELS[camera]
    return turns


def change_times(frames: np.ndarray, fps: float, *, k: int = 4, min_gap_s: float = 0.4,
                 avoid_s: list[float] | None = None) -> list[float]:
    """Times just after the k largest colour-histogram steps (the moments a
    drift, cut or jump is most likely visible), at least min_gap_s apart from
    each other and from avoid_s (e.g. the uniform sample times)."""
    n = int(frames.shape[0])
    if n < 4 or k <= 0:
        return []
    hists = np.array([_hist(f) for f in frames])
    steps = np.abs(np.diff(hists, axis=0)).sum(1) / 6.0
    taken = list(avoid_s or [])
    chosen: list[float] = []
    for t in np.argsort(-steps):
        if t < CUT_SKIP_FRAMES:
            continue
        sec = round(float(t + 1) / fps, 3)
        if all(abs(sec - other) >= min_gap_s for other in taken):
            chosen.append(sec)
            taken.append(sec)
            if len(chosen) == k:
                break
    return sorted(chosen)


def extract_frames_at(video: Path, times: list[float], out_dir: Path, tag: str = "c") -> list[Path]:
    """Full-resolution PNGs at the given seconds, named ..._<tag><i>_<sec>s.png
    so frame_times_from_names() can read the timestamps back."""
    import hashlib

    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(str(video).encode()).hexdigest()[:10]
    paths = []
    for i, sec in enumerate(times):
        target = out_dir / f"{Path(video).stem}_{digest}_{tag}{i:02d}_{sec:.3f}s.png"
        if not target.exists():
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(video), "-ss", f"{sec:.3f}", "-frames:v", "1",
                 "-c:v", "png", "-y", str(target)],
                check=True, capture_output=True, timeout=60,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        paths.append(target)
    return paths


def detect_frame_faults(video: Path) -> dict[str, Any]:
    fps = 24.0
    try:
        rate = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=avg_frame_rate", "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.strip()
        num, _, den = rate.partition("/")
        fps = float(num) / float(den or 1) or 24.0
    except Exception:
        pass
    return frame_signals(_decode_small(Path(video)), fps=fps)


# ------------------------------------------------------------------ VLM prompt

CHECK_KEYS = (
    "requested_subject_visible",
    "same_place_in_all_frames",
    "abrupt_cut_between_frames",
    "same_time_of_day_in_all_frames",
    "subject_count_matches_brief",
    "visual_medium_matches_brief",
    "text_or_logo_visible",
    # 2026-09-25: the rig / operator in the picture was the wrong_viewpoint
    # false-pass family that 24q left open (D02 614e, D01 3032, c036).
    "camera_or_operator_visible",
)

VIDEO_JUDGE_SYSTEM_PROMPT = """You are a strict video-quality judge. You receive a BRIEF (what the client asked for), its CONSTRAINTS, and frames sampled in time order from one generated clip.

Judge the frames against the BRIEF and CONSTRAINTS only. Look at every frame, including the last ones. Generated clips often fail by: showing a different subject than the brief, cutting to a different shot, drifting to a different place, changing from day to night, adding extra people or animals, switching visual medium (photo vs 2D drawing vs pixel art vs 3D render), showing text or a logo, or showing the recording rig itself (a camera, a tripod, the drone that should be carrying the camera, or the operator) in the picture.

Work in this order and return ONE JSON object, nothing else, no markdown:
{
  "frames": ["F1: <what is visible: main subject and how many, place, light and time of day, visual medium, and any camera, drone, tripod or person holding a camera that is itself an object in the picture>", "F2: ...", one entry per frame],
  "checks": {
    "requested_subject_visible": "yes" or "no",        (is the main subject of the BRIEF clearly visible in most frames?)
    "same_place_in_all_frames": "yes" or "no",         (do all frames show the same location, with no switch to a different room, landscape or set?)
    "abrupt_cut_between_frames": "yes" or "no",        (does any frame jump to an unrelated shot compared with the frame before it?)
    "same_time_of_day_in_all_frames": "yes" or "no",   (no change such as golden hour to midday, or dusk to night?)
    "subject_count_matches_brief": "yes" or "no",      (no extra or missing people, animals or objects compared with the BRIEF and CONSTRAINTS?)
    "visual_medium_matches_brief": "yes" or "no",      (photo / 2D illustration / cel animation / pixel art / 3D render / ink drawing as the BRIEF asks? If the BRIEF names no medium, answer "yes": any realistic look is fine)
    "text_or_logo_visible": "yes" or "no",             (any letters, words, signs or logos that the BRIEF does not ask for?)
    "camera_or_operator_visible": "yes" or "no",       (answer from the pictures only, not from the BRIEF: is any recording equipment or its operator IN the picture in any frame: a camera or camcorder body, a lens, a tripod or light stand, a drone / quadcopter / aircraft seen from outside (from behind, beside, above or below it, flying ahead of the camera), a boom, a monitor, or a person holding, carrying or looking through a camera or camcorder? If a drone is an object in the picture, the camera is not on that drone, whatever the BRIEF calls the shot: "yes". If a person is holding a camcorder in the picture, that person is the operator: "yes". A view seen THROUGH a camera or drone with none of this in the picture is "no", and a still, locked-off framing is "no": the fault is the rig or operator appearing in the image, not the shot being static)
    "constraint_broken": "<quote the CONSTRAINT that is broken, or none>"
  },
  "text_video_alignment": <number 0.00-1.00>,
  "temporal_consistency": <number 0.00-1.00>,
  "aesthetic_quality": <number 0.00-1.00>,
  "rationale": {"text_video_alignment": "<one sentence>", "temporal_consistency": "<one sentence>", "aesthetic_quality": "<one sentence>"}
}

Lighting and camera moves: if the BRIEF asks for a flicker, strobe, lights going out, a dead tube or any lighting change, a frame that is only darker or brighter than its neighbours, with the same walls, floor, doors and layout, is that requested effect. It is not a different place and not a cut. If the BRIEF asks the camera to turn, approach or look at a wall, floor or object, a later frame showing that surface close up in the same room is that move, not a cut. Answer same_place_in_all_frames "no" or abrupt_cut_between_frames "yes" only when the setting itself changes to somewhere else, never for the light level or the framing alone.

Scoring: 0.00 total failure, 0.50 mixed, 1.00 excellent. text_video_alignment = the BRIEF's subject, setting, action and style are all there. temporal_consistency = one continuous shot with stable identity, place, geometry and light. aesthetic_quality = composition, focus, detail, no artifacts. Describe what you see; do not copy the BRIEF's wording. Do not include a pass field.
"""


def build_judge_system_prompt(*, literal_mode: bool = False, literal_rule: str | None = None) -> str:
    if not literal_mode:
        return VIDEO_JUDGE_SYSTEM_PROMPT
    from media_accuracy_gate import literal_override_block

    return VIDEO_JUDGE_SYSTEM_PROMPT + literal_override_block(literal_rule)


_FRAME_TIME = re.compile(r"_(\d+(?:\.\d+)?)s\.png$", re.I)


def frame_times_from_names(frames: list[Path]) -> list[float] | None:
    """extract_eval_frames names files ..._<index>_<seconds>s.png."""
    times = []
    for frame in frames:
        match = _FRAME_TIME.search(Path(frame).name)
        if not match:
            return None
        times.append(float(match.group(1)))
    return times


def _frame_light(t: float, spans: list) -> str:
    for start, end, kind in spans or []:
        if float(start) - 0.03 <= t <= float(end) + 0.03:
            return str(kind)
    return ""


# 2026-09-25l: read to the VLM once when any sampled frame follows a measured
# rigid turn. An instrument reading plus how to read it; the reservation in
# the last sentence keeps a real place change a place change.
TURN_RULE = (
    "A measured turn is an instrument reading: the whole picture slid between those two frames, as it "
    "does when the camera pans or tilts within one continuous shot. A wall, floor, ceiling or object of "
    "the same room or scene filling the later frame after a turn is that camera move: not a cut, not a "
    "new place, and still the BRIEF's setting. Answer abrupt_cut_between_frames \"yes\" or "
    "same_place_in_all_frames \"no\" across a measured turn only if the setting itself is somewhere else "
    "(another room, landscape or set)."
)


def build_judge_user_prompt(*, brief: str, constraints: str, frame_times: list[float] | None,
                            signals: dict[str, Any] | None = None) -> str:
    parts = [f"BRIEF: {brief.strip()}", f"CONSTRAINTS: {constraints.strip() or 'none stated'}"]
    if frame_times:
        spans = (signals or {}).get("dark_spans_s") or []
        turns = measured_turns((signals or {}).get("camera_moves"))
        stamps, marked, turned = [], 0, 0
        for i, t in enumerate(frame_times):
            notes = []
            kind = _frame_light(t, spans)
            if kind:
                marked += 1
                notes.append(f"{kind}: lights down in this frame, measured")
            if i + 1 in turns:
                turned += 1
                notes.append(f"camera {turns[i + 1]} between F{i} and F{i + 1}, measured")
            stamps.append(f"F{i + 1}={t:.1f}s ({'; '.join(notes)})" if notes else f"F{i + 1}={t:.1f}s")
        parts.append(f"FRAMES ({len(frame_times)}, in time order): {', '.join(stamps)}")
        if marked:
            parts.append("A near-black or dim frame is a lighting dip in the same shot, not a new place and not a "
                         "cut: judge place, cuts and the subject from the lit frames.")
        if turned:
            parts.append(TURN_RULE)
    return "\n".join(parts)


# ------------------------------------------------------------------ caps

_STYLIZED = re.compile(
    r"\b(2d|anime|cel[- ]shad\w*|cartoon|watercolou?r|pixel[- ]art|\d+-bit|sprite|ink|hatch\w*|"
    r"woodblock|ukiyo-e|illustrat\w*|painting|painted|graphic[- ]novel|comic|sketch|claymation|"
    r"stop[- ]motion|3d render|cgi|low[- ]poly)\b", re.I)
_TEXT_WORDS = re.compile(r"\b(text|sign|signage|logo|letter|title|caption|kanji|neon|word|label)\w*", re.I)
# A brief that has the actor handle or inspect the gear asks for it to be in
# the picture (c013: "in front of the tripod ... checks everything on the tripod
# (tripod legs, cable)"; the sitcom pack's "grips the camera body", "examining
# the tripod legs"). "camcorder on a locked tripod", "no camera body in frame"
# and "no tripod lock" describe the viewpoint or forbid the gear: they do not
# match, so the check still binds on those briefs. The bare words camera /
# camcorder are deliberately not in the noun list: "in front of the camera" is
# the viewpoint camera in every audition brief.
_GEAR_REQUESTED = re.compile(
    r"\b(?:examin\w*|inspect\w*|check\w*|grip\w*|grab\w*|hold\w*|adjust\w*|touch\w*|"
    r"look\w* at|in front of|beside|next to|crouch\w*)\W+(?:\w+\W+){0,3}?"
    r"(?:tripod|camera body|camcorder body|light stand|boom|rig|lens)\b", re.I)
_NO = {"no", "false", "n"}
_YES = {"yes", "true", "y"}


def _answer(value: Any) -> str | None:
    word = str(value or "").strip().lower().split(" ")[0].strip(".,;:!\"'")
    if word in _YES:
        return "yes"
    if word in _NO:
        return "no"
    return None


def normalize_checks(verdict: Any) -> dict[str, Any]:
    raw = verdict.get("checks") if isinstance(verdict, dict) else None
    raw = raw if isinstance(raw, dict) else {}
    checks: dict[str, Any] = {key: _answer(raw.get(key)) for key in CHECK_KEYS}
    broken = str(raw.get("constraint_broken") or "").strip()
    checks["constraint_broken"] = (
        None if broken.lower().strip(".") in {"", "none", "no", "n/a", "null"} else broken[:200]
    )
    return checks


def _real_constraint_quote(quote: str | None, constraints: str) -> bool:
    """The VLM sometimes dumps its check answers into constraint_broken, or
    invents a constraint when none was given; neither counts."""
    if not quote or not constraints.strip():
        return False
    return not any(key in quote for key in CHECK_KEYS)


def fault_caps(checks: dict[str, Any], signals: dict[str, Any] | None, brief: str = "",
               constraints: str = "") -> dict[str, dict]:
    """Axis -> {cap, why}. The lowest applicable cap per axis wins."""
    caps: dict[str, dict] = {}

    def cap(axis: str, value: float, why: str) -> None:
        if axis not in caps or value < caps[axis]["cap"]:
            caps[axis] = {"cap": value, "why": why}

    if checks.get("requested_subject_visible") == "no":
        cap("text_video_alignment", 0.20, "requested subject not visible")
    # The rig, the drone that should carry the camera, or the operator in the
    # picture: the clip shows the camera instead of being the camera. 0.25 sits
    # between "subject absent" (0.20: nothing requested is there) and "wrong
    # medium" (0.30: the scene is there in the wrong form); here the scene is
    # usually there, seen from the wrong side. Any cap <= 0.40 already fails
    # both curriculum bars; the value only orders rejects among themselves.
    if checks.get("camera_or_operator_visible") == "yes" and not _GEAR_REQUESTED.search(f"{brief} {constraints}"):
        cap("text_video_alignment", 0.25, "camera rig, drone or operator visible in frame")
    # Photo vs "3D render" is not a reliable call for this VLM on photoreal
    # briefs (it called clean Backrooms hallways 3D renders); the medium check
    # only binds when the brief asks for a stylized medium.
    if checks.get("visual_medium_matches_brief") == "no" and _STYLIZED.search(f"{brief} {constraints}"):
        cap("text_video_alignment", 0.30, "visual medium does not match the brief")
    if checks.get("subject_count_matches_brief") == "no":
        cap("text_video_alignment", 0.40, "extra or missing subjects")
    if _real_constraint_quote(checks.get("constraint_broken"), constraints):
        cap("text_video_alignment", 0.40, f"constraint broken: {checks['constraint_broken']}")
    if checks.get("text_or_logo_visible") == "yes" and not _TEXT_WORDS.search(brief or ""):
        cap("text_video_alignment", 0.30, "text or logo the brief did not ask for")
        cap("aesthetic_quality", 0.40, "text or logo the brief did not ask for")
    if checks.get("same_place_in_all_frames") == "no":
        cap("temporal_consistency", 0.30, "location changes between frames")
    if checks.get("abrupt_cut_between_frames") == "yes":
        cap("temporal_consistency", 0.30, "abrupt cut between frames")
    if checks.get("same_time_of_day_in_all_frames") == "no":
        cap("temporal_consistency", 0.40, "time of day changes")
    if signals:
        if signals.get("hard_cuts_s"):
            cap("temporal_consistency", 0.25, f"hard cut detected at {signals['hard_cuts_s']} s (frame difference)")
        if float(signals.get("blank_fraction") or 0.0) >= BLANK_MIN_FRACTION:
            # Aesthetic only: a brief can legitimately ask for a dark scene.
            cap("aesthetic_quality", 0.20, f"{signals['blank_fraction']:.0%} of frames are near-black")
    return caps


def apply_fault_caps(parsed: dict, signals: dict[str, Any] | None, brief: str = "",
                     constraints: str = "") -> dict:
    """Bound parsed VLM scores by the fault checks. Returns a new dict in the
    parse_video_director_scores shape plus checks/caps/scores_vlm/signals."""
    out = dict(parsed)
    checks = normalize_checks(parsed.get("verdict"))
    caps = fault_caps(checks, signals, brief, constraints)
    out["checks"] = checks
    out["signals"] = signals
    out["caps"] = caps
    scores = parsed.get("scores")
    if not isinstance(scores, dict) or len(scores) != len(AXES):
        return out
    missing = [key for key in CHECK_KEYS if checks.get(key) is None]
    out["scores_vlm"] = dict(scores)
    capped = {axis: round(min(float(scores[axis]), caps.get(axis, {}).get("cap", 1.0)), 4) for axis in AXES}
    values = [capped[a] for a in AXES]
    out["scores"] = capped
    out["mean"] = round(sum(values) / len(values), 4)
    out["minimum"] = round(min(values), 4)
    if missing:
        out["reasons"] = list(out.get("reasons") or []) + [f"fault checks unanswered: {', '.join(missing)}"]
    return out


# ------------------------------------------------------------------ retry
#
# 2026-09-25k. Two ways the answer arrives without the three scores, both seen
# on the labeled sets and in the live pass (CHANGELOG 2026-09-25g/h/i): the
# frame lines run away into repetition until num_predict and the JSON never
# closes (D03 5c73, D02 53ae), or the JSON closes after the checks and before
# the scores (br_c001 32ce). Either is "VLM scores rejected" in the live
# metric, a failure penalty below every judged clip, for a clip that may be
# good (53ae scored 0.92 live). One retry, same frames, with more room and a
# short neutral note (frame lines under 15 words; close the JSON after the
# scores). The first call is unchanged, so a clip that parses first time is
# judged as before.
#
# Measured (judge_eval_20260925/retry_arms*.jsonl): any anti-repetition
# pressure on the retry, a "never repeat a phrase" note or repeat_penalty
# 1.05 / 1.08, flips a good continuous clip (D02 53ae 1.00/1.00/0.90 -> same
# place "no", cut "yes", min 0.25) because the VLM varies near-identical frame
# lines and then reads its own variation as change; 1.08 also closed the JSON
# early again (br_c001 32ce). Dropping the per-frame scratchpad fails every
# good clip (M03 4110 0.95 -> 0.40, B01 644b 0.80 -> 0.30). The neutral note
# at 1.0 kept M03 (1.00/1.00/0.90) and B01 (1.00/1.00/0.80) at their first-
# attempt scores and every reject rejected, so the penalty stays at the
# judge's validated 1.0 (CHANGELOG 2026-09-24ae) and the escape from a loop
# is the changed prompt, not the sampler. The failures are stochastic on a
# fixed prompt (each named clip parsed on other runs of the same prompt).
# 2026-09-25n measured, 2026-09-25o applied: llama-server keeps the shared
# prefix (the system prompt's KV, computed in the launch's first request's
# batch) for every later request unless told not to, and the answer depends
# on that state. Cold (a fresh launch: the live metric's condition, every
# time) and warm (every eval-runner clip after the first) differed in wording
# on ~90% of clips and in verdict on 4 of 79 labeled clips plus two phase C
# renders (D02 7d15 reject cold, pass warm; D02 53ae parses cold, loops
# warm); each condition alone reproduced byte for byte (cold 29/29 across
# launches; the 7 live phase C rows 7/7 identical cold offline). The judge
# sends cache_prompt False on every call, first attempt and retry, so a
# judgement is the same cold prefill wherever it runs and whatever the
# server saw before it. Cost: ~10.6k tokens prefilled instead of ~9.3k,
# about 0.3 s per clip.
JUDGE_CACHE_PROMPT = False
JUDGE_RETRY_REPEAT_PENALTY = 1.0
JUDGE_RETRY_NUM_PREDICT = 2048
JUDGE_RETRY_NOTE = (
    "RETRY: the previous answer for these frames ended before the three scores. "
    "Keep each frame line under 15 words. Close the JSON object only after "
    "text_video_alignment, temporal_consistency, aesthetic_quality and rationale."
)


def scores_missing(parsed: dict | None) -> bool:
    """True when the parse failed for want of the three float scores (a runaway
    or an early close), the one failure a retry can fix. A verdict from the
    wrong model or runtime is not retried, whatever else it lacks."""
    if not isinstance(parsed, dict) or parsed.get("status") == "pass":
        return False
    reasons = [str(reason) for reason in parsed.get("reasons") or []]
    if any("not from the exact" in reason for reason in reasons):
        return False
    return any("float score" in reason for reason in reasons)


def retry_user_prompt(prompt: str) -> str:
    """The first attempt's user prompt with the retry note appended."""
    return f"{prompt.rstrip()}\n{JUDGE_RETRY_NOTE}"
