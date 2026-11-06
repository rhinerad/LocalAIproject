"""Deterministic preflight gate for generated prompt-pack stills.

This is deliberately mechanical: it catches malformed/blank/cropped outputs and
prompt-control violations before a still can feed the video stage. Semantic VLM
review is recorded as not-run unless the exact approved VLM is explicitly invoked.
Mechanical pass alone never authorizes approval; semantic_check not_run maps to
approval_status unapproved.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def semantic_verdict_from_caption(caption: str, prompt: str, *, model: str | None = None,
                                  runtime: str | None = None) -> dict:
    """Validate a structured exact-VLM verdict; fail closed on plain prose.

    The VLM must return JSON with ``pass``, ``rationale`` and ``observed``.
    This function is deliberately separate from mechanical image checks so a
    generic caption can never be mistaken for prompt-grounded QA.
    """
    reasons = []
    if model != "qwen25-vl-nsfw-caption:v4-q4_k_m" or runtime != "llama.cpp":
        reasons.append("semantic verdict is not from the exact Qwen2.5-VL Caption V4 llama.cpp runtime")
    try:
        raw = str(caption).strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "", 1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Some VLM builds prepend a short sentence despite “JSON only”.
            # Recover a single balanced object, but still validate its schema
            # below; arbitrary prose can never pass the gate.
            start, end = raw.find("{"), raw.rfind("}")
            if start < 0 or end <= start:
                raise
            data = json.loads(raw[start:end + 1])
    except Exception:
        data = None
        reasons.append("VLM did not return structured JSON")

    if not isinstance(data, dict):
        reasons.append("VLM structured output was not a JSON object")
        return {"status": "fail", "model": model, "runtime": runtime,
                "verdict": None, "reasons": reasons}

    if not isinstance(data.get("pass"), bool):
        reasons.append("missing boolean pass field")
    if not isinstance(data.get("rationale"), str) or not data.get("rationale", "").strip():
        reasons.append("missing rationale")
    if not isinstance(data.get("observed"), dict):
        reasons.append("missing observed evidence object")
    checks = data.get("checks")
    required_checks = (
        "requested_subjects_present",
        "requested_pose_or_action_visible",
        "requested_composition_visible",
        "setting_matches",
        "identity_continuity",
        "no_forbidden_equipment",
        "blind_observation_consistent",
    )
    if not isinstance(checks, dict):
        reasons.append("missing prompt-grounded checks object")
    else:
        for name in required_checks:
            if not isinstance(checks.get(name), bool):
                reasons.append(f"missing boolean semantic check: {name}")
            elif checks[name] is False:
                reasons.append(f"semantic check failed: {name}")
    if data.get("pass") is False:
        reasons.append(data.get("rationale") or "VLM rejected the image")
    return {"status": "pass" if not reasons else "fail", "model": model,
            "runtime": runtime, "verdict": data, "reasons": reasons}


VIDEO_DIRECTOR_SCORE_KEYS = (
    "text_video_alignment",
    "temporal_consistency",
    "aesthetic_quality",
)

# Inject this as the llama.cpp / Qwen2.5-VL system prompt. Thresholding is
# applied in Python (progressive curriculum); the VLM must not emit `pass`.
VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT = """You are a strict video-quality judge for a local FLUX.1 + MiniMax I2V director.

You will receive (1) a START_FRAME_BASELINE still description, (2) a VIDEO_MOTION_PROMPT, and (3) sampled frames in chronological order from a single clip.

There is NO end_prompt. Score text_video_alignment solely on how well the video executes the motion and camera behavior described in VIDEO_MOTION_PROMPT, using START_FRAME_BASELINE only as the expected opening look (subject, setting, style).

Score ONLY what is visible in the frames. Do not reward the prompt's poetry. Do not invent unseen motion. Do not average in how hard the prompt was.

Return ONE JSON object and nothing else. No markdown fences. No preface. No trailing commentary.

Required schema:
{
  "text_video_alignment": <float 0.00 to 1.00>,
  "temporal_consistency": <float 0.00 to 1.00>,
  "aesthetic_quality": <float 0.00 to 1.00>,
  "rationale": {
    "text_video_alignment": "<one sentence>",
    "temporal_consistency": "<one sentence>",
    "aesthetic_quality": "<one sentence>"
  }
}

Scoring rules:
- Every score is a JSON number, not a string. Use two decimal places.
- 0.00 = total failure of that axis. 0.50 = mixed or partial. 1.00 = excellent and unambiguous.
- text_video_alignment: the camera move, subject motion, pace, and actions named in VIDEO_MOTION_PROMPT appear across the frames; the opening look should be compatible with START_FRAME_BASELINE. Penalize frozen stills when motion was requested, wrong direction/pace, and missing camera behavior.
- temporal_consistency: identity, geometry, and lighting hold across frames; motion is physically plausible; no flicker, morph, teleport, identity swap, or random scene change.
- aesthetic_quality: composition, color, focus, and artifact load. Penalize watermarks, burned-in text, crushed detail, muddy frames, and plastic over-smoothing.

Do not include a boolean pass field. Do not include cfg, denoise, or step counts. Downstream Python applies a progressive threshold (0.60 early, tightening to 0.85).
"""


# iteration 0-2: 0.60, 3-5: 0.70, 6+: 0.80.
# The strict bar was 0.85 (iteration 9+) until 2026-09-24. The fixed judge
# (video_judge.py, CHANGELOG 2026-09-24q/r) scores correct Backrooms-batch
# clips at aesthetic 0.80-0.85, so at 0.85 8 of 12 good held-out clips failed
# for a scoring-range mismatch rather than a defect. Operator decision: 0.80.
_CURRICULUM_STEPS = (
    (0, 0.60),
    (3, 0.70),
    (6, 0.80),
)


def curriculum_threshold(iteration: int) -> float:
    """Progressive pass bar for Generalized Video Director scoring."""
    try:
        step = int(iteration)
    except (TypeError, ValueError):
        step = 0
    if step < 0:
        step = 0
    threshold = _CURRICULUM_STEPS[0][1]
    for start, value in _CURRICULUM_STEPS:
        if step >= start:
            threshold = value
    return float(threshold)


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)
_AXIS_PATTERNS = {
    "text_video_alignment": (
        r"text[_\s-]*video[_\s-]*alignment",
        r"text[_\s-]*alignment",
        r"\balignment\b",
    ),
    "temporal_consistency": (
        r"temporal[_\s-]*consistency",
        r"temporal[_\s-]*score",
        r"\btemporal\b",
    ),
    "aesthetic_quality": (
        r"aesthetic[_\s-]*quality",
        r"aesthetic[_\s-]*score",
        r"\baesthetic\b",
    ),
}


def _strip_markdown_fences(raw: str) -> str:
    text = str(raw or "").strip()
    fenced = _FENCE_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    return text


def _extract_json_object(raw: str) -> dict | None:
    text = _strip_markdown_fences(raw)
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    blob = text[start:end + 1]
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        repaired = blob.replace("'", '"')
        try:
            data = json.loads(repaired)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None


def _scan_axis_scores(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for key, patterns in _AXIS_PATTERNS.items():
        for pattern in patterns:
            match = re.search(
                pattern + r"\s*(?:score|rating|axis)?\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%?",
                text,
                re.IGNORECASE,
            )
            if not match:
                continue
            parsed = _score_to_unit_float(match.group(1))
            if parsed is None:
                continue
            found[key] = parsed
            break
    return found


def _extract_scores_from_prose(raw: str) -> dict[str, float]:
    """Pull axis floats from messy Caption V4 prose when JSON is missing."""
    text = str(raw or "")
    fenced = _FENCE_RE.search(text)
    if fenced:
        outside = text[:fenced.start()] + "\n" + text[fenced.end():]
        outside_found = _scan_axis_scores(outside)
        if outside_found:
            return outside_found
        inner = _scan_axis_scores(fenced.group(1))
        if inner:
            return inner
    return _scan_axis_scores(_strip_markdown_fences(text) or text)


def _score_to_unit_float(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value).strip())
        if not match:
            return None
        number = float(match.group(0))
    if number != number:
        return None
    if number > 1.0 and number <= 100.0:
        number = number / 100.0
    if number < 0.0 or number > 1.0:
        return None
    return round(number, 4)



def build_video_director_vlm_system_prompt(
    *,
    literal_mode: bool = False,
    literal_rule: str | None = None,
) -> str:
    """VLM system prompt with optional clip-specific hard rule.

    When literal_mode is True (bypass_director / literal_prompt overrides),
    inject a highest-priority *positive* verification requirement. Do not name
    rejected aesthetics — naming them primes the VLM to hallucinate them.
    """
    base = VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT
    if not literal_mode:
        return base
    return base + literal_override_block(literal_rule)


def literal_override_block(literal_rule: str | None = None) -> str:
    """Highest-priority literal-clip rule appended to a judge system prompt.

    Shared by the holistic prompt above and the fault-checked judge in
    video_judge.py.
    """
    rule = (literal_rule or "").strip() or (
        "VERIFICATION REQUIREMENT: This clip depicts a normal residential room "
        "(bedroom or living room) with blue walls and domestic furniture. "
        "Verify that domestic items (bed, posters, windows, furniture) are clearly visible. "
        "Score text_video_alignment high only when those domestic cues are present."
    )
    return (
        "\n\n=== CLIP-SPECIFIC OVERRIDE (HIGHEST PRIORITY) ===\n"
        + rule
        + "\nDescribe only what is visible. Prefer positive scene confirmation over listing absences.\n"
        + "If the required domestic residential cues are missing, set text_video_alignment <= 0.10 "
        + "and say which expected domestic items are absent.\n"
    )

def build_vlm_user_prompt(
    *,
    start_prompt: str,
    video_prompt: str,
    literal_mode: bool = False,
    expected_scene: str | None = None,
) -> str:
    parts = [
        f"START_FRAME_BASELINE: {start_prompt}",
        f"VIDEO_MOTION_PROMPT: {video_prompt}",
    ]
    if literal_mode:
        detail = (expected_scene or start_prompt or "").strip()[:800]
        parts.append(
            "VERIFICATION_FOCUS: Confirm a normal residential interior "
            "(bedroom or living room) with blue walls, daylight from a window, "
            "and visible domestic items such as a bed, posters, desk/lamp, and ordinary furniture."
        )
        if detail:
            parts.append(f"EXPECTED_SCENE_DETAIL: {detail}")
        parts.append(
            "SCORING_HINT: Give text_video_alignment >= 0.90 when the frames clearly show "
            "those domestic residential cues matching START_FRAME_BASELINE and VIDEO_MOTION_PROMPT. "
            "If those domestic cues are missing, score text_video_alignment <= 0.10 and name what is absent."
        )
    return "\n".join(parts)


def parse_video_director_scores(
    caption: str,
    prompt: str = "",
    *,
    model: str | None = None,
    runtime: str | None = None,
) -> dict:
    """Parse Qwen2.5-VL float scores for the three director axes. Fail-closed."""
    reasons = []
    if model != "qwen25-vl-nsfw-caption:v4-q4_k_m" or runtime != "llama.cpp":
        reasons.append(
            "video-director verdict is not from the exact Qwen2.5-VL Caption V4 llama.cpp runtime"
        )
    raw_text = str(caption or "")
    data = _extract_json_object(raw_text)
    scores = {}
    if isinstance(data, dict):
        for key in VIDEO_DIRECTOR_SCORE_KEYS:
            parsed = _score_to_unit_float(data.get(key))
            if parsed is not None:
                scores[key] = parsed
    prose_scores = _extract_scores_from_prose(raw_text)
    if prose_scores:
        json_all_zero = bool(scores) and all(scores.get(key, 0.0) == 0.0 for key in VIDEO_DIRECTOR_SCORE_KEYS)
        for key, value in prose_scores.items():
            if key not in scores or (json_all_zero and value > 0.0):
                scores[key] = value
        if json_all_zero and any(prose_scores.get(key, 0.0) > 0.0 for key in VIDEO_DIRECTOR_SCORE_KEYS):
            reasons.append("JSON scores were all 0.00; used prose/regex extractor")
    if data is None and not prose_scores:
        reasons.append("VLM did not return a JSON object with float scores")
        return {
            "status": "fail",
            "model": model,
            "runtime": runtime,
            "scores": None,
            "mean": None,
            "minimum": None,
            "verdict": None,
            "raw": raw_text[:4000],
            "reasons": reasons,
            "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest() if prompt else None,
        }
    for key in VIDEO_DIRECTOR_SCORE_KEYS:
        if key not in scores:
            reasons.append(f"missing or invalid float score: {key}")
    rationale = data.get("rationale") if isinstance(data, dict) else None
    if rationale is not None and not isinstance(rationale, (str, dict)):
        reasons.append("rationale must be a string or object")
    if len(scores) != len(VIDEO_DIRECTOR_SCORE_KEYS):
        return {
            "status": "fail",
            "model": model,
            "runtime": runtime,
            "scores": scores or None,
            "mean": None,
            "minimum": None,
            "verdict": data,
            "raw": raw_text[:4000],
            "reasons": reasons,
            "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest() if prompt else None,
        }
    values = [scores[key] for key in VIDEO_DIRECTOR_SCORE_KEYS]
    mean = round(sum(values) / len(values), 4)
    minimum = round(min(values), 4)
    return {
        "status": "fail" if reasons else "pass",
        "model": model,
        "runtime": runtime,
        "scores": scores,
        "mean": mean,
        "minimum": minimum,
        "verdict": data,
        "raw": raw_text[:4000],
        "reasons": reasons,
        "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest() if prompt else None,
    }


def video_director_passes_curriculum(
    parsed: dict,
    iteration: int,
    *,
    use_minimum: bool = True,
) -> dict:
    """Apply the progressive bar. Default: every axis must clear the threshold."""
    threshold = curriculum_threshold(iteration)
    try:
        step = int(iteration)
    except (TypeError, ValueError):
        step = 0
    reasons = list(parsed.get("reasons") or [])
    if parsed.get("status") != "pass" or not parsed.get("scores"):
        reasons.append("scores were not parsed as a passing structured verdict")
        return {
            "pass": False,
            "threshold": threshold,
            "iteration": step,
            "compared": None,
            "reasons": reasons,
        }
    compared = float(parsed["minimum"] if use_minimum else parsed["mean"])
    ok = compared >= threshold
    if not ok:
        axis = "minimum" if use_minimum else "mean"
        reasons.append(
            f"{axis} score {compared:.2f} below curriculum threshold {threshold:.2f}"
        )
    return {
        "pass": ok,
        "threshold": threshold,
        "iteration": step,
        "compared": compared,
        "reasons": reasons,
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prompt_assertions(prompt: str, clip_id: str, frame: str) -> dict:
    p = str(prompt or "").lower()
    cid = str(clip_id or "").upper()
    reasons = []
    # Stills must never contain action/motion instructions.
    if re.search(r"\b(actor|entity)\s+(?:walks?|runs?|moves?|turns?|waves?|leans?|approaches?|falls?|spins?)\b", p):
        reasons.append("still prompt contains motion instruction")
    # Ignore meta language like "those belong only in the video prompt".
    if re.search(r"\bminimax\b", p) or re.search(r"\bvideo prompt\s*:", p):
        reasons.append("still prompt contains video-only language")
    # A camera noun inside a prohibitive clause is not a positive camera
    # request.  In particular, Mode-B scene plates use prose such as
    # "Do not depict ... visible camera body, lens, tripod ..." where a simple
    # one-word lookbehind would incorrectly flag the word "visible".
    positive_visibility_scope = re.sub(
        r"\b(?:do not depict|do not show|never show|no)\b[^.]*\.", "", p
    )
    if re.search(r"\b(?:visible|shown|showing|see)\s+(?:the\s+)?(?:camera|camcorder|lens|tripod)\b", positive_visibility_scope):
        reasons.append("prompt positively requests visible camera equipment")
    if re.search(r"\b(?:visible|shown|showing)\s+(?:recording\s+)?(?:camera|camcorder|lens|tripod)\b", positive_visibility_scope):
        reasons.append("prompt positively requests visible camera equipment")
    n = int(cid[1:]) if cid and cid[1:].isdigit() else None
    # C015 start is still the apartment; the fall lands in Backrooms on C015 last.
    if n is not None and (n <= 14 or (n == 15 and str(frame).lower() == "start")):
        if "apartment" not in p:
            reasons.append("C001-C014/C015-start still must specify apartment")
        if re.search(r"\bbachal_", p) or ("required backrooms sdxl lora" in p):
            reasons.append("pre-fall still must not use Backrooms LoRA")
    elif n is not None:
        if "backrooms" not in p and "yellow wallpaper" not in p and "yellow" not in p:
            reasons.append("post-fall still lacks Backrooms/yellow environment cue")
    # Scene-plate prompts intentionally omit filming vocabulary so diffusion
    # models do not draw cameras or crews. Either legacy camcorder control or
    # the newer viewer/scene-plate control is sufficient.
    if not any(token in p for token in (
            "camcorder", "viewer-perspective framing", "clean scene plate")):
        reasons.append("still lacks viewpoint control")
    # Mode B (C016-C062): prompt must hard-forbid actor face/torso.
    if n is not None and 16 <= n <= 62:
        if not re.search(r"do not depict (?:(?:the|a|an) )?(?:actor's )?face(?:\s+or\s+|,\s*)torso|never shown", p):
            reasons.append("Mode B still prompt missing face/torso hard reject language")
    return {"pass": not reasons, "reasons": reasons}


def video_prompt_assertions(
    prompt: str,
    *,
    camera_locked: bool = False,
    scene_spec: str = "",
) -> dict:
    """Mechanical checks for Phase-1 *video* prompts (Wan FLF motion).

    Unlike ``prompt_assertions``, motion verbs are required, not forbidden.
    Missing physics tokens fail the candidate so MIPRO/GEPA can learn them
    instead of a post-hoc ``enforce_physics_terms`` rewrite.
    """
    p = str(prompt or "").lower()
    spec = str(scene_spec or "").lower()
    reasons = []
    if len(p.strip()) < 24:
        reasons.append("video prompt is too short to drive Wan FLF")
    locked = bool(camera_locked)
    if not locked:
        if "handheld walking momentum" not in p:
            reasons.append("unlocked camera missing handheld walking momentum")
        if "first-person camcorder tracking" not in p and "handheld" not in p:
            reasons.append("unlocked camera missing handheld/camcorder tracking language")
        if "vhs" not in p and "1990s" not in p:
            reasons.append("missing analog VHS or 1990s home-video texture")
        if "continuous unbroken shot" not in p and "unbroken" not in p:
            reasons.append("missing continuous/unbroken-shot cue")
    else:
        if "handheld walking momentum" in p:
            reasons.append("locked camera should not include handheld walking momentum")
    if spec:
        if any(token in spec for token in ("backrooms", "yellow", "hallway", "carpet", "wallpaper")):
            if not any(token in p for token in ("backrooms", "yellow", "hallway", "carpet", "wallpaper")):
                reasons.append("scene spec is Level 0 / hallway but prompt lacks those cues")
        if "pool" in spec and "pool" not in p and "water" not in p:
            reasons.append("scene spec is a pool room but prompt lacks pool/water cues")
    return {"pass": not reasons, "reasons": reasons}


def check_video(video_path: str | Path, prompt: str = "", clip_id: str = "") -> dict:
    """Mechanical MP4 gate. Does not load the VLM."""
    import subprocess

    path = Path(video_path)
    reasons = []
    checks = {
        "exists": path.is_file(),
        "min_size": False,
        "decodable": False,
        "has_video_stream": False,
        "min_frames": False,
    }
    if not path.is_file():
        reasons.append("video file does not exist")
    else:
        size = path.stat().st_size
        checks["min_size"] = size >= 10_000
        if not checks["min_size"]:
            reasons.append(f"video too small: {size} bytes")
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            raw = subprocess.check_output(
                [
                    "ffprobe", "-v", "error", "-show_streams", "-show_format",
                    "-of", "json", str(path),
                ],
                text=True, encoding="utf-8", timeout=30, creationflags=flags,
            )
            data = json.loads(raw)
            streams = data.get("streams") or []
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            checks["decodable"] = bool(streams)
            checks["has_video_stream"] = bool(video_streams)
            frames = 0
            if video_streams:
                try:
                    frames = int(video_streams[0].get("nb_frames") or 0)
                except (TypeError, ValueError):
                    frames = 0
            checks["min_frames"] = frames > 0
            if not checks["has_video_stream"]:
                reasons.append("no video stream")
            if not checks["min_frames"]:
                reasons.append("video has zero frames")
        except Exception as exc:
            reasons.append(f"ffprobe failed: {exc}")
    pa = video_prompt_assertions(prompt) if prompt else {"pass": True, "reasons": []}
    if prompt:
        reasons.extend(pa["reasons"])
    mechanical_pass = not reasons and all(checks.values())
    return {
        "status": "pass" if mechanical_pass else "fail",
        "clip_id": clip_id,
        "video_path": str(path),
        "video_sha256": _sha256(path) if path.is_file() else None,
        "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest() if prompt else None,
        "checks": checks,
        "prompt_assertions": pa,
        "semantic_check": "not_run",
        "qa_status": "pending_semantic" if mechanical_pass else "fail",
        "approval_status": "unapproved",
        "reasons": reasons,
    }


def check_still(image_path: str | Path, prompt: str, clip_id: str, frame: str) -> dict:
    path = Path(image_path)
    reasons = []
    checks = {"exists": path.is_file(), "decodable": False, "dimensions": False, "non_blank": False, "aspect_4_3": False}
    if not path.is_file():
        reasons.append("image file does not exist")
    else:
        try:
            from PIL import Image, ImageStat
            with Image.open(path) as im:
                im.verify()
            with Image.open(path) as im:
                w, h = im.size
                checks["decodable"] = True
                checks["dimensions"] = w >= 512 and h >= 384
                checks["aspect_4_3"] = abs((w / h) - (4 / 3)) <= 0.08
                stat = ImageStat.Stat(im.convert("RGB"))
                checks["non_blank"] = max(stat.var) >= 20.0
                if not checks["dimensions"]:
                    reasons.append(f"dimensions too small: {w}x{h}")
                if not checks["aspect_4_3"]:
                    reasons.append(f"unexpected aspect ratio: {w}x{h}")
                if not checks["non_blank"]:
                    reasons.append("image is near-uniform/blank")
        except Exception as exc:
            reasons.append(f"image decode failed: {exc}")
    pa = prompt_assertions(prompt, clip_id, frame)
    reasons.extend(pa["reasons"])
    mechanical_pass = not reasons and all(checks.values())
    return {
        "status": "pass" if mechanical_pass else "fail",
        "clip_id": clip_id,
        "frame": frame,
        "image_path": str(path),
        "image_sha256": _sha256(path) if path.is_file() else None,
        "prompt_sha256": hashlib.sha256(str(prompt).encode()).hexdigest(),
        "checks": checks,
        "prompt_assertions": pa,
        "semantic_check": "not_run",
        "semantic_reason": "Exact Qwen2.5-VL Caption V4 lazy llama.cpp review has not run.",
        "qa_status": "pending_semantic" if mechanical_pass else "fail",
        # not_run semantic QA is fail-closed: never treat mechanical pass as approved.
        "approval_status": "unapproved",
        "reasons": reasons,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--clip", required=True)
    ap.add_argument("--frame", choices=("start", "last"), required=True)
    args = ap.parse_args(argv)
    result = check_still(args.image, args.prompt, args.clip, args.frame)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
