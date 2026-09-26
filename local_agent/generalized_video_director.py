#!/usr/bin/env python3
"""Generalized Video Director — Phase 2 mock MIPROv2 loop.

DSPy writes Wan prompts and three ComfyUI hyperparameters (cfg_scale,
denoise, step_count). The metric clamps those floats, then scores a *mocked*
Qwen2.5-VL JSON payload. No ComfyUI, no VLM, no VRAM flip-flop.

Curriculum bar (architect-approved): min(alignment, temporal, aesthetic)
must clear the progressive threshold. CFG category bands stay soft.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

from media_accuracy_gate import (
    VIDEO_DIRECTOR_SCORE_KEYS,
    VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT,
    curriculum_threshold,
    parse_video_director_scores,
    video_director_passes_curriculum,
)

# Legal ranges for Wan 2.1 FLF / I2V on a 16 GB card. Phase 2 must clamp
# *before* graph injection; GEPA/MIPRO will still emit out-of-range strings.
CFG_SCALE_RANGE = (1.0, 8.0)
DENOISE_RANGE = (1.0, 1.0)  # FLUX Empty Latent: fixed full denoise
STEP_COUNT_RANGE = (16.0, 40.0)
DEFAULT_HPARAMS = {
    "cfg_scale": 5.5,
    "denoise": 0.85,
    "step_count": 28.0,
}

CATEGORIES = (
    "drone_high_kinematics",
    "macro_nature",
    "stylized_2d",
    "backrooms",
)

HERE = Path(__file__).resolve().parent
DEFAULT_MOCK_SAVE = (
    HERE.parent / "models" / "dspy_compiled" / "generalized_video_director_mipro_mock.json"
)
EXACT_VLM_MODEL = "qwen25-vl-nsfw-caption:v4-q4_k_m"
EXACT_VLM_RUNTIME = "llama.cpp"

# Last metric dict. MIPROv2 only sees the float; tests and logs read this.
LAST_METRIC_RESULT: dict[str, Any] = {}

DIRECTOR_SIGNATURE_INSTRUCTIONS = (
    'You are a Generalized Video Director for FLUX.1 (start frame) + MiniMax '
    'Image-to-Video on an RTX 5080. Emit start_prompt, video_prompt, '
    'negative_prompt, and numeric hparams cfg_scale and step_count only.\n'
    'start_prompt is sent to the still-image model. Write highly descriptive '
    'natural language for a SINGLE still opening frame. Focus on lighting, '
    'texture, materials, composition, lens/look. No camera-move verbs.\n'
    'video_prompt is sent to the image-to-video model. Focus STRICTLY on camera '
    'physics, subject motion, and temporal change across an 8-second / 192-frame '
    'clip. Name move, pace, and ending energy. Do not rewrite the whole scene '
    'from scratch.\n'
    'Each prompt value is only the scene description itself. Never begin it '
    'with a label, a field name, or a model name.\n'
    'Do NOT emit denoise — FLUX Empty Latent T2I always uses denoise=1.0.\n'
    'Do NOT emit end_prompt.\n'
    'Honor category:\n'
    '- drone_high_kinematics: aerial/high-speed travel, large parallax; prefer '
    'cfg_scale 4.0-5.5; step_count 24-32.\n'
    '- macro_nature: extreme close-up, shallow DOF, slow organic motion; prefer '
    'cfg_scale 5.5-7.0; step_count 28-36.\n'
    '- stylized_2d: lock the named 2D medium every frame; prefer cfg_scale 6.0-7.5; '
    'step_count 20-30.\n'
    '- backrooms: first-person analog camcorder unless locked; prefer cfg_scale '
    '5.0-6.5; step_count 24-32. Put camera nouns AND motion verbs in video_prompt; '
    'put VHS/liminal look in start_prompt.\n'
    'cfg_scale and step_count MUST be JSON numbers (floats). cfg_scale in [1.0, 8.0], '
    'step_count in [16, 40].'
)


# 16-row Beta Set. Inputs only — no gold prompts. Five clips per generalized
# category plus one Backrooms retention row so MIPRO cannot drop that domain.
BETA_SET: list[dict[str, Any]] = [
    # --- drone / high-kinematics (VBench: dynamic degree, motion smoothness,
    # temporal flickering, human action, scene) ---
    {
        "id": "GVD-D01",
        "category": "drone_high_kinematics",
        "vbench_focus": "dynamic_degree, scene, motion_smoothness",
        "motion_class": "aerial_push_in",
        "duration_seconds": 8.0,
        "user_intent": (
            "A cinematic drone shot flies in from the open ocean toward sheer "
            "Atlantic cliffs at golden hour, revealing nested seabirds and "
            "white spray against black basalt."
        ),
        "constraints": (
            "Continuous aerial move, no tripod lock, no still photograph, "
            "no text, no watermark, no people on the cliff edge."
        ),
    },
    {
        "id": "GVD-D02",
        "category": "drone_high_kinematics",
        "vbench_focus": "motion_smoothness, temporal_flickering, dynamic_degree",
        "motion_class": "fpv_canopy_thread",
        "duration_seconds": 6.0,
        "user_intent": (
            "First-person FPV drone threads a dense pine canopy at high speed, "
            "weaving between trunks with motion blur on needles and a sudden "
            "break into a sunlit clearing."
        ),
        "constraints": (
            "Unbroken FPV take, no crash cut, no morphing trees, no HUD, "
            "no on-screen flight data."
        ),
    },
    {
        "id": "GVD-D03",
        "category": "drone_high_kinematics",
        "vbench_focus": "human_action, motion_smoothness, dynamic_degree",
        "motion_class": "vehicle_chase_track",
        "duration_seconds": 8.0,
        "user_intent": (
            "A tracking shot races beside a motorcycle carving a switchback "
            "canyon road; dust rooster-tails off the rear tire as the rider "
            "leans into a hairpin above a dry riverbed."
        ),
        "constraints": (
            "One rider, one bike, no camera body in frame, no jump cuts, "
            "no identity swap of the rider mid-clip."
        ),
    },
    {
        "id": "GVD-D04",
        "category": "drone_high_kinematics",
        "vbench_focus": "human_action, dynamic_degree, temporal_flickering",
        "motion_class": "action_slow_motion",
        "duration_seconds": 4.0,
        "user_intent": (
            "Slow-motion skateboard kickflip in an empty concrete plaza at "
            "blue hour; the board rotates fully under the skater and lands "
            "with a visible compression of the trucks."
        ),
        "constraints": (
            "Single trick, single skater, no crowd, no logo on the board, "
            "no frozen freeze-frame posing as video."
        ),
    },
    {
        "id": "GVD-D05",
        "category": "drone_high_kinematics",
        "vbench_focus": "spatial_relationship, scene, motion_smoothness",
        "motion_class": "helicopter_orbit",
        "duration_seconds": 8.0,
        "user_intent": (
            "A helicopter-style orbit around a glass skyscraper at night; "
            "reflections of city lights slide across the facade while the "
            "camera holds a constant radius and slowly descends."
        ),
        "constraints": (
            "Orbit only, no crash zoom, no interior cutaway, no readable "
            "signage, no aircraft visible in frame."
        ),
    },
    # --- macro / nature (VBench: subject consistency, imaging quality,
    # object class, scene, temporal consistency of small motion) ---
    {
        "id": "GVD-M01",
        "category": "macro_nature",
        "vbench_focus": "imaging_quality, subject_consistency, object_class",
        "motion_class": "static_macro_shimmer",
        "duration_seconds": 6.0,
        "user_intent": (
            "Extreme macro of dew beads on a spider's silk at sunrise; each "
            "droplet holds an inverted garden, and a faint breeze makes the "
            "web tremble without breaking the droplets."
        ),
        "constraints": (
            "No spider body required, no humans, no camera shake from a "
            "handheld operator, no rack-focus jump, no text."
        ),
    },
    {
        "id": "GVD-M02",
        "category": "macro_nature",
        "vbench_focus": "object_class, motion_smoothness, subject_consistency",
        "motion_class": "insect_foraging",
        "duration_seconds": 6.0,
        "user_intent": (
            "A honeybee lands on a purple coneflower, packs orange pollen "
            "onto its hind legs, and lifts off in a short hover, all in "
            "shallow depth of field with creamy bokeh."
        ),
        "constraints": (
            "One bee, one flower species, no time-lapse jump, no extra "
            "insects, no human hands."
        ),
    },
    {
        "id": "GVD-M03",
        "category": "macro_nature",
        "vbench_focus": "scene, temporal_consistency, imaging_quality",
        "motion_class": "flowing_water",
        "duration_seconds": 8.0,
        "user_intent": (
            "A close view of a clear creek sliding over mossy stones in a "
            "temperate forest; caustics crawl across wet rock while a fern "
            "frond dips into the current and springs back."
        ),
        "constraints": (
            "Locked or gently drifting macro, no drone altitude, no animals "
            "larger than an insect, no plastic sheen on the water."
        ),
    },
    {
        "id": "GVD-M04",
        "category": "macro_nature",
        "vbench_focus": "subject_consistency, temporal_style, object_class",
        "motion_class": "metamorphosis",
        "duration_seconds": 8.0,
        "user_intent": (
            "A monarch butterfly slowly unfolds crumpled wet wings from a "
            "chrysalis hanging on a milkweed stem; wings expand and flatten "
            "without teleporting to a dry adult."
        ),
        "constraints": (
            "One chrysalis, one butterfly, no time-lapse dissolve that skips "
            "the unfolding, no extra butterflies, no human."
        ),
    },
    {
        "id": "GVD-M05",
        "category": "macro_nature",
        "vbench_focus": "imaging_quality, dynamic_degree, temporal_flickering",
        "motion_class": "impact_ripple",
        "duration_seconds": 4.0,
        "user_intent": (
            "A single raindrop strikes a broad hosta leaf; the impact crown "
            "forms, the leaf flexes, and a silver rivulet runs toward the tip."
        ),
        "constraints": (
            "One drop event, no storm-wide cutaways, no sky replacement, "
            "no slow-motion morphing of the leaf shape."
        ),
    },
    # --- stylized / 2D (VBench: appearance style, temporal style,
    # aesthetic quality, overall consistency) ---
    {
        "id": "GVD-S01",
        "category": "stylized_2d",
        "vbench_focus": "appearance_style, aesthetic_quality, temporal_style",
        "motion_class": "looping_print",
        "duration_seconds": 6.0,
        "user_intent": (
            "An ukiyo-e woodblock wave in the style of a crashing great wave; "
            "foam claws rise and fall in a looping 2D print, with visible "
            "baren texture and limited mineral pigments, never photoreal water."
        ),
        "constraints": (
            "Stay 2D woodblock for every frame, no 3D CGI ocean, no live-action "
            "plate, no watermark, no modern ships."
        ),
    },
    {
        "id": "GVD-S02",
        "category": "stylized_2d",
        "vbench_focus": "appearance_style, temporal_style, scene",
        "motion_class": "cel_walkthrough",
        "duration_seconds": 8.0,
        "user_intent": (
            "A cel-shaded anime night city: a lone figure walks under neon "
            "kanji reflections on wet asphalt, hard color holds, thin ink "
            "outlines, no photoreal skin or ray-traced glass."
        ),
        "constraints": (
            "Cel shading locked, no live-action mix, no readable brand logos, "
            "no 3D turnaround that breaks the 2D plane."
        ),
    },
    {
        "id": "GVD-S03",
        "category": "stylized_2d",
        "vbench_focus": "aesthetic_quality, temporal_style, appearance_style",
        "motion_class": "medium_dissolve",
        "duration_seconds": 6.0,
        "user_intent": (
            "A watercolor mountain valley in spring; wet-on-wet pigment blooms "
            "and a paper-grain wash slowly reveals a distant torii as the "
            "paint settles, remaining a painting at all times."
        ),
        "constraints": (
            "Paper and pigment only, no photoreal landscape underneath, no "
            "camera drone, no text in the sky."
        ),
    },
    {
        "id": "GVD-S04",
        "category": "stylized_2d",
        "vbench_focus": "appearance_style, overall_consistency, scene",
        "motion_class": "pixel_explore",
        "duration_seconds": 6.0,
        "user_intent": (
            "A 16-bit pixel-art dungeon corridor with torch flicker and a "
            "tiny adventurer walking away from camera; sprite scale, palette, "
            "and tile grid stay consistent, no high-res 3D interpolation."
        ),
        "constraints": (
            "Pixel grid locked, no anti-aliased 3D, no UI HUD, no modern "
            "photographs of stone."
        ),
    },
    {
        "id": "GVD-S05",
        "category": "stylized_2d",
        "vbench_focus": "temporal_style, human_action, aesthetic_quality",
        "motion_class": "graphic_novel_duel",
        "duration_seconds": 8.0,
        "user_intent": (
            "A black-and-white graphic-novel duel on a rain-slick rooftop; "
            "heavy ink hatching, speed lines on the lunge, two silhouetted "
            "fencers, no photoreal faces and no color except a single red panel "
            "accent on the spark of clashing blades."
        ),
        "constraints": (
            "Ink-and-hatch 2D only, no live-action, no gore close-up, no "
            "readable captions or speech balloons."
        ),
    },
    # --- retention row: keep Backrooms physics in the generalized director ---
    {
        "id": "GVD-B01",
        "category": "backrooms",
        "vbench_focus": "temporal_consistency, scene, motion_smoothness",
        "motion_class": "handheld_walk",
        "duration_seconds": 8.0,
        "user_intent": (
            "Handheld first-person camcorder walk down a damp yellow Level 0 "
            "Backrooms hallway; fluorescent rectangles repeat into the distance "
            "over wet brown-beige carpet and sickly wallpaper."
        ),
        "constraints": (
            "Unlocked handheld camera. Include handheld walking momentum, "
            "first-person camcorder tracking, heavy VHS artifacting, a continuous "
            "unbroken shot, realistic camera shake, and 1990s home video aesthetic. "
            "No actor face or torso, no apartment furniture, no readable text."
        ),
        "start_prompt": (
            "1990s VHS camcorder footage, found footage, first-person perspective looking down an empty, dimly lit yellow wallpapered hallway with damp carpet. Heavy VHS tracking noise, chromatic aberration, grainy tape artifacts, liminal space."
        ),
        "end_prompt": (
            "1990s VHS camcorder footage, found footage, first-person perspective situated 20 feet further down the same yellow hallway, having walked forward toward a corridor turn. Heavy VHS tracking noise, chromatic aberration, grainy tape artifacts, liminal space."
        ),
    },
]


def _dspy():
    try:
        import dspy
        return dspy
    except ImportError as exc:
        raise RuntimeError(
            "dspy is not installed. Beta-set and metric helpers work without "
            "it; build_director_program needs `pip install dspy`."
        ) from exc


def director_signature_class():
    """Return the typed DSPy Signature class (not an instance)."""
    dspy = _dspy()

    class GeneralizedVideoDirectorSignature(dspy.Signature):
        """Direct FLUX.1 start frame + MiniMax I2V motion (no end_prompt, no denoise)."""

        user_intent: str = dspy.InputField(
            desc="The user's scene, subject, and motion request"
        )
        category: str = dspy.InputField(
            desc="One of drone_high_kinematics, macro_nature, stylized_2d, backrooms"
        )
        vbench_focus: str = dspy.InputField(
            desc="Comma-separated VBench axes this clip must satisfy"
        )
        duration_seconds: float = dspy.InputField(
            desc="Clip length in seconds (8 for MiniMax 192 frames)"
        )
        constraints: str = dspy.InputField(
            desc="Hard rejection clauses the prompt must honor"
        )
        start_prompt: str = dspy.OutputField(
            desc="Describe the opening still of this clip in your own words"
        )
        video_prompt: str = dspy.OutputField(
            desc="Describe how the camera and subject move over this clip in your own words"
        )
        negative_prompt: str = dspy.OutputField(
            desc="Comma-separated failure modes to suppress"
        )
        cfg_scale: float = dspy.OutputField(
            desc="FLUX KSampler CFG, JSON float in [1.0, 8.0]"
        )
        step_count: float = dspy.OutputField(
            desc="FLUX KSampler steps as a float in [16, 40]; rounded to int later"
        )

    GeneralizedVideoDirectorSignature.instructions = DIRECTOR_SIGNATURE_INSTRUCTIONS
    return GeneralizedVideoDirectorSignature


def build_director_program():
    """ChainOfThought director. No compile, no metric loop."""
    dspy = _dspy()
    signature = director_signature_class()

    class GeneralizedVideoDirector(dspy.Module):
        def __init__(self):
            super().__init__()
            self.director = dspy.ChainOfThought(signature)

        def forward(
            self,
            user_intent,
            category,
            vbench_focus="",
            duration_seconds=8.0,
            constraints="",
        ):
            return self.director(
                user_intent=user_intent,
                category=category,
                vbench_focus=vbench_focus or "",
                duration_seconds=float(duration_seconds),
                constraints=constraints or "",
            )

    return GeneralizedVideoDirector()


def _coerce_float(value: Any, default: float, lo: float, hi: float) -> float:
    if isinstance(value, bool) or value is None:
        number = default
    elif isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, dict):
        lo_v = value.get("min", value.get("low", value.get("lo", value.get("start"))))
        hi_v = value.get("max", value.get("high", value.get("hi", value.get("end"))))
        try:
            lo_n = float(lo_v)
            hi_n = float(hi_v)
            number = (lo_n + hi_n) / 2.0
        except (TypeError, ValueError):
            match = re.search(r"-?\d+(?:\.\d+)?", str(value))
            number = float(match.group(0)) if match else default
    else:
        text = str(value).strip()
        range_match = re.search(
            r"(-?\d+(?:\.\d+)?)\s*(?:-|to|\.\.)\s*(-?\d+(?:\.\d+)?)",
            text,
            flags=re.IGNORECASE,
        )
        if range_match:
            number = (float(range_match.group(1)) + float(range_match.group(2))) / 2.0
        else:
            match = re.search(r"-?\d+(?:\.\d+)?", text)
            number = float(match.group(0)) if match else default
    if number != number:  # NaN
        number = default
    return max(lo, min(hi, number))


def _pred_field(pred: Any, name: str) -> Any:
    if isinstance(pred, dict):
        return pred.get(name)
    return getattr(pred, name, None)


def clamp_director_hparams(pred: Any) -> dict[str, float]:
    """Coerce LM text into in-range floats. Does not talk to ComfyUI."""
    return {
        "cfg_scale": _coerce_float(
            _pred_field(pred, "cfg_scale"),
            DEFAULT_HPARAMS["cfg_scale"],
            CFG_SCALE_RANGE[0],
            CFG_SCALE_RANGE[1],
        ),
        "denoise": _coerce_float(
            _pred_field(pred, "denoise"),
            DEFAULT_HPARAMS["denoise"],
            DENOISE_RANGE[0],
            DENOISE_RANGE[1],
        ),
        "step_count": _coerce_float(
            _pred_field(pred, "step_count"),
            DEFAULT_HPARAMS["step_count"],
            STEP_COUNT_RANGE[0],
            STEP_COUNT_RANGE[1],
        ),
    }
    # unreachable fallback
def beta_set_rows() -> list[dict[str, Any]]:
    """Copy of the 16-prompt Beta Set for review and DSPy Example wrap."""
    return [dict(row) for row in BETA_SET]


def beta_set_by_category() -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {key: [] for key in CATEGORIES}
    for row in BETA_SET:
        grouped.setdefault(str(row["category"]), []).append(dict(row))
    return grouped


_STOPWORDS = frozenset({
    "that", "this", "with", "from", "into", "over", "under", "then", "than",
    "them", "they", "their", "there", "have", "been", "will", "onto", "each",
    "only", "down", "across", "while", "about", "after", "before", "between",
})
_MOTION_CUES = (
    "walk", "orbit", "fly", "flight", "unfold", "drip", "track", "handheld",
    "drone", "fpv", "kickflip", "hover", "push", "thread", "chase", "lunge",
    "flicker", "ripple", "bloom", "descend", "rotate", "momentum",
)


def _example_field(example: Any, name: str) -> Any:
    return _pred_field(example, name)


def _mock_scoring_texts(pred: Any) -> tuple[str, str]:
    """(scene text, motion text) for mock scoring, lowercased.

    Current signature: start_prompt (FLUX still) + video_prompt (MiniMax I2V)
    form the scene text; video_prompt alone carries camera/subject motion.
    Legacy Wan predictions with only positive_prompt use it for both.
    """
    start = str(_pred_field(pred, "start_prompt") or "").strip().lower()
    video = str(_pred_field(pred, "video_prompt") or "").strip().lower()
    if start or video:
        return f"{start} {video}".strip(), video
    legacy = str(_pred_field(pred, "positive_prompt") or "").strip().lower()
    return legacy, legacy


def mock_vlm_scores(example: Any, pred: Any, hparams: dict[str, float]) -> dict[str, float]:
    """Deterministic stand-in for Qwen2.5-VL. No GPU. No network."""
    intent = str(_example_field(example, "user_intent") or "").lower()
    scene_text, motion_text = _mock_scoring_texts(pred)
    negative = str(_pred_field(pred, "negative_prompt") or "").lower()
    category = str(_example_field(example, "category") or "").strip().lower()

    tokens = [
        tok for tok in re.findall(r"[a-z]{4,}", intent)
        if tok not in _STOPWORDS
    ]
    if not scene_text.strip():
        alignment = 0.05
    elif not tokens:
        alignment = 0.40
    else:
        hits = sum(1 for tok in tokens if tok in scene_text)
        alignment = 0.35 + 0.60 * (hits / len(tokens))

    motion = any(cue in motion_text for cue in _MOTION_CUES)
    temporal = 0.72 if motion else 0.42
    if len(motion_text) >= 80:
        temporal = min(1.0, temporal + 0.08)

    aesthetic = 0.50
    if negative:
        aesthetic += 0.15
    if CFG_SCALE_RANGE[0] <= hparams["cfg_scale"] <= CFG_SCALE_RANGE[1]:
        aesthetic += 0.08
    if DENOISE_RANGE[0] <= hparams["denoise"] <= DENOISE_RANGE[1]:
        aesthetic += 0.07
    if "watermark" in negative or "text" in negative:
        aesthetic += 0.05

    if category == "backrooms":
        if "handheld walking momentum" in motion_text:
            temporal = min(1.0, temporal + 0.16)
        else:
            temporal = min(temporal, 0.48)
        if "yellow" in scene_text or "backrooms" in scene_text:
            alignment = min(1.0, alignment + 0.08)
    elif category == "stylized_2d":
        style_lock = any(
            token in scene_text
            for token in ("ukiyo", "cel", "watercolor", "pixel", "ink", "woodblock")
        )
        if not style_lock:
            alignment = min(alignment, 0.55)
    elif category == "drone_high_kinematics":
        if hparams["cfg_scale"] > 6.5:
            temporal = min(temporal, 0.58)

    def _unit(value: float) -> float:
        return round(max(0.0, min(1.0, value)), 2)

    return {
        "text_video_alignment": _unit(alignment),
        "temporal_consistency": _unit(temporal),
        "aesthetic_quality": _unit(aesthetic),
    }


def mock_vlm_caption(scores: dict[str, float], *, rationale: str = "mock VLM") -> str:
    """JSON the real parser accepts, with the exact Caption V4 identity applied later."""
    payload = {
        **scores,
        "rationale": {
            key: f"{rationale}: {key.replace('_', ' ')}={scores[key]:.2f}"
            for key in VIDEO_DIRECTOR_SCORE_KEYS
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def evaluate_director_candidate(
    example: Any,
    pred: Any,
    *,
    iteration: int | None = None,
) -> dict[str, Any]:
    """Clamp hparams, mock the VLM, parse through the production JSON contract."""
    if iteration is None:
        raw_iter = os.environ.get("GVD_CURRICULUM_ITERATION", "0")
        try:
            iteration = int(raw_iter)
        except (TypeError, ValueError):
            iteration = 0
    hparams = clamp_director_hparams(pred)
    scores = mock_vlm_scores(example, pred, hparams)
    caption = mock_vlm_caption(scores)
    parsed = parse_video_director_scores(
        caption,
        str(_example_field(example, "user_intent") or ""),
        model=EXACT_VLM_MODEL,
        runtime=EXACT_VLM_RUNTIME,
    )
    curriculum = video_director_passes_curriculum(parsed, iteration, use_minimum=True)
    minimum = parsed.get("minimum")
    mipro = float(minimum) if parsed.get("status") == "pass" and minimum is not None else 0.0
    clip_id = str(
        _example_field(example, "id")
        or _example_field(example, "clip_id")
        or ""
    )
    feedback = {
        "mock": True,
        "clip_id": clip_id,
        "category": str(_example_field(example, "category") or ""),
        "hparams": hparams,
        "step_count_int": int(round(hparams["step_count"])),
        "scores": parsed.get("scores") or scores,
        "mean": parsed.get("mean"),
        "minimum": parsed.get("minimum"),
        "threshold": curriculum["threshold"],
        "iteration": curriculum["iteration"],
        "passes_curriculum": bool(curriculum["pass"]),
        "mipro": mipro,
        "reasons": list(curriculum.get("reasons") or parsed.get("reasons") or []),
    }
    return {
        "mipro": mipro,
        "passes_curriculum": bool(curriculum["pass"]),
        "hparams": hparams,
        "scores": parsed.get("scores") or scores,
        "parsed": parsed,
        "curriculum": curriculum,
        "feedback": json.dumps(feedback, ensure_ascii=True),
        "feedback_obj": feedback,
    }


def generalized_video_metric(
    example,
    pred,
    trace=None,
    pred_name=None,
    pred_trace=None,
    **_kwargs,
) -> float:
    """MIPROv2 contract: scalar in [0, 1]. JSON feedback is on LAST_METRIC_RESULT."""
    global LAST_METRIC_RESULT
    result = evaluate_director_candidate(example, pred)
    LAST_METRIC_RESULT = result
    generalized_video_metric.last_feedback = result["feedback"]
    generalized_video_metric.last_result = result
    return float(result["mipro"])


generalized_video_metric.last_feedback = "{}"
generalized_video_metric.last_result = {}


def load_beta_trainset(rows: list[dict[str, Any]] | None = None):
    """Wrap Beta Set dicts as DSPy Examples. Inputs match the Signature."""
    dspy = _dspy()
    examples = []
    for row in rows or BETA_SET:
        examples.append(
            dspy.Example(
                user_intent=str(row.get("user_intent") or ""),
                category=str(row.get("category") or ""),
                vbench_focus=str(row.get("vbench_focus") or ""),
                duration_seconds=float(row.get("duration_seconds") or 8.0),
                constraints=str(row.get("constraints") or ""),
                id=str(row.get("id") or ""),
                motion_class=str(row.get("motion_class") or ""),
                start_prompt=str(row.get("start_prompt") or ""),
                end_prompt=str(row.get("end_prompt") or ""),
            ).with_inputs(
                "user_intent",
                "category",
                "vbench_focus",
                "duration_seconds",
                "constraints",
            )
        )
    if not examples:
        raise RuntimeError("Beta Set is empty")
    return examples


def build_mock_lm():
    """Return a DummyLM subclass that never exhausts and always type-fills."""
    dspy = _dspy()
    from dspy.adapters.chat_adapter import field_header_pattern
    from dspy.dsp.utils.utils import dotdict
    from dspy.utils.dummies import DummyLM

    class MockDirectorLM(DummyLM):
        def __init__(self):
            super().__init__([{"answer": "unused"}])
            self._header_re = field_header_pattern

        def _slice_field(self, content: str, name: str) -> str:
            match = re.search(
                rf"\[\[ ## {re.escape(name)} ## \]\]\s*(.*?)(?=\n\[\[ ## |\Z)",
                content,
                re.DOTALL | re.IGNORECASE,
            )
            return match.group(1).strip() if match else ""

        def _defaults(self, content: str) -> dict[str, Any]:
            intent = self._slice_field(content, "user_intent") or "a cinematic video shot"
            category = (self._slice_field(content, "category") or "").strip().lower()
            positive = (
                f"{intent} Continuous camera motion, consistent lighting, "
                "no morphing identities, no jump cuts."
            )
            # FLUX.1 still (look) + MiniMax I2V (motion) fields, current signature.
            start = (
                f"{intent} Single opening frame, consistent lighting, "
                "detailed textures, clear composition."
            )
            video = (
                "Camera tracks forward across one continuous unbroken take, "
                "steady pace, no morphing identities, no jump cuts."
            )
            if "backrooms" in category or "backrooms" in content.lower():
                positive += (
                    " First-person camcorder tracking, heavy VHS artifacting, "
                    "handheld walking momentum, continuous unbroken shot, "
                    "realistic camera shake, 1990s home video aesthetic, "
                    "sickly yellow wallpaper."
                )
                start += (
                    " Heavy VHS artifacting, 1990s home video aesthetic, "
                    "sickly yellow wallpaper, buzzing fluorescent Backrooms corridor."
                )
                video += (
                    " First-person camcorder tracking, handheld walking momentum, "
                    "realistic camera shake."
                )
            return {
                "reasoning": (
                    "Mock director: restate the request, pick category-legal "
                    "hparams as JSON floats, keep motion in one take."
                ),
                "positive_prompt": positive,  # legacy Wan field
                "start_prompt": start,
                "video_prompt": video,
                "negative_prompt": (
                    "blur, morph, watermark, readable text, jump cut, still "
                    "photograph, identity swap, extra subjects"
                ),
                "cfg_scale": 5.5,
                "denoise": 0.85,
                "step_count": 28.0,
                "proposed_instruction": DIRECTOR_SIGNATURE_INSTRUCTIONS,
                "program_description": (
                    "A Generalized Video Director that writes Wan prompts and "
                    "CFG/denoise/step floats."
                ),
                "module_description": "ChainOfThought director predictor.",
                "observations": (
                    "Sixteen clips: drone, macro, stylized 2D, one Backrooms "
                    "retention row."
                ),
                "summary": (
                    "Beta Set spans high-kinematics, macro nature, 2D style "
                    "lock, and one analog Backrooms walk."
                ),
                "dataset_description": (
                    "16 user-intent rows for Wan first-last-frame direction."
                ),
            }

        def forward(self, prompt=None, messages=None, **kwargs):
            messages = messages or [{"role": "user", "content": prompt or ""}]
            content = str((messages[-1] or {}).get("content") or "")
            defaults = self._defaults(content)
            mentioned = [
                name for name in defaults
                if f"## {name} ##" in content.lower() or name in content.lower()
            ]
            if not mentioned:
                mentioned = [
                    "start_prompt", "video_prompt", "negative_prompt",
                    "cfg_scale", "step_count",
                ]
            if "reasoning" in content.lower() and "reasoning" not in mentioned:
                mentioned = ["reasoning", *mentioned]
            payload = {name: defaults[name] for name in mentioned if name in defaults}
            for extra in self._header_re.findall(content):
                if extra not in payload and extra in defaults:
                    payload[extra] = defaults[extra]
                elif extra not in payload:
                    payload[extra] = defaults.get("reasoning", "mock")
            formatted = self._format_answer_fields(payload)
            n = int(kwargs.get("n") or self.kwargs.get("n") or 1)
            choices = [
                dotdict(
                    message=dotdict(content=formatted, tool_calls=None),
                    finish_reason="stop",
                )
                for _ in range(max(1, n))
            ]
            return dotdict(
                choices=choices,
                usage=dotdict(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                model="dummy",
            )

    return MockDirectorLM()


def configure_mock_lms():
    """CPU-only student + proposer. Does not touch Ollama, xAI, or ComfyUI."""
    dspy = _dspy()
    lm = build_mock_lm()
    dspy.configure(lm=lm)
    return lm, lm


def compile_director(
    *,
    mock: bool = True,
    auto: str | None = None,
    trainset=None,
    valset=None,
    save_path: Path | None = None,
    log_dir: Path | None = None,
    num_candidates: int = 1,
    num_trials: int = 1,
    max_bootstrapped_demos: int = 0,
    max_labeled_demos: int = 0,
):
    """Run MIPROv2. Phase 2 default is mock LM + 1 trial, no GPU."""
    dspy = _dspy()
    if not mock:
        raise RuntimeError(
            "Live ComfyUI/VLM compile is Phase 3. Re-run with mock=True "
            "(the default) until the VRAM controller is approved."
        )
    if auto not in {None, "light", "medium", "heavy"}:
        raise ValueError("auto must be None, light, medium, or heavy")
    task_lm, prompt_lm = configure_mock_lms()
    student = build_director_program()
    trainset = list(trainset or load_beta_trainset())
    valset = list(valset or trainset)
    log_dir = Path(log_dir or (HERE / "runtime" / "dspy_opt" / "gvd_logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    save_path = Path(save_path or DEFAULT_MOCK_SAVE)
    save_path.parent.mkdir(parents=True, exist_ok=True)

    optimizer_kwargs: dict[str, Any] = {
        "metric": generalized_video_metric,
        "prompt_model": prompt_lm,
        "task_model": task_lm,
        "num_threads": 1,
        "max_bootstrapped_demos": max_bootstrapped_demos,
        "max_labeled_demos": max_labeled_demos,
        "track_stats": True,
        "log_dir": str(log_dir),
        "seed": 9,
    }
    if auto is None:
        optimizer_kwargs["auto"] = None
        optimizer_kwargs["num_candidates"] = num_candidates
    else:
        optimizer_kwargs["auto"] = auto

    teleprompter = dspy.MIPROv2(**optimizer_kwargs)
    compile_kwargs: dict[str, Any] = {
        "trainset": trainset,
        "valset": valset,
        "minibatch": False,
        "program_aware_proposer": False,
        "data_aware_proposer": False,
        "tip_aware_proposer": False,
        "fewshot_aware_proposer": False,
        "max_bootstrapped_demos": max_bootstrapped_demos,
        "max_labeled_demos": max_labeled_demos,
    }
    if auto is None:
        compile_kwargs["num_trials"] = num_trials
    compiled = teleprompter.compile(student, **compile_kwargs)
    compiled.save(str(save_path))
    return compiled, save_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Phase 2: MIPROv2 compile of GeneralizedVideoDirector against a "
            "mocked VLM metric. No ComfyUI, no VRAM controller."
        ),
    )
    parser.add_argument(
        "--compile",
        action="store_true",
        help="Run MIPROv2. Refused without this flag.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=True,
        help="Use MockDirectorLM (default). Live inference is not wired yet.",
    )
    parser.add_argument(
        "--auto",
        choices=("light", "medium", "heavy"),
        default=None,
        help="MIPROv2 auto mode. Default for mock is 1 candidate / 1 trial.",
    )
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--candidates", type=int, default=1)
    parser.add_argument("--save", type=Path, default=None)
    args = parser.parse_args(argv)
    if not args.compile:
        parser.print_help()
        print(
            "\nRefusing to start without --compile.\n"
            "Mock MIPROv2 (CPU, no ComfyUI):\n"
            "  python local_agent/generalized_video_director.py --compile --mock\n"
        )
        return 2
    compiled, path = compile_director(
        mock=True,
        auto=args.auto,
        save_path=args.save,
        num_candidates=args.candidates,
        num_trials=args.trials,
    )
    print(json.dumps({
        "saved": str(path),
        "optimizer": "mipro",
        "mock": True,
        "auto": args.auto,
        "trials": args.trials if args.auto is None else "auto",
        "trainset": len(BETA_SET),
        "last_feedback": generalized_video_metric.last_feedback,
    }, indent=2))
    return 0 if compiled is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())


# Re-export gate symbols so Phase 2 has one import surface.
__all__ = [
    "BETA_SET",
    "CATEGORIES",
    "CFG_SCALE_RANGE",
    "DEFAULT_HPARAMS",
    "DEFAULT_MOCK_SAVE",
    "DENOISE_RANGE",
    "DIRECTOR_SIGNATURE_INSTRUCTIONS",
    "LAST_METRIC_RESULT",
    "STEP_COUNT_RANGE",
    "VIDEO_DIRECTOR_SCORE_KEYS",
    "VIDEO_DIRECTOR_VLM_SYSTEM_PROMPT",
    "beta_set_by_category",
    "beta_set_rows",
    "build_director_program",
    "build_mock_lm",
    "clamp_director_hparams",
    "compile_director",
    "configure_mock_lms",
    "curriculum_threshold",
    "director_signature_class",
    "evaluate_director_candidate",
    "generalized_video_metric",
    "load_beta_trainset",
    "mock_vlm_caption",
    "mock_vlm_scores",
    "parse_video_director_scores",
    "video_director_passes_curriculum",
]
