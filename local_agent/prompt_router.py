"""Prompt dialect formatter for local image and video targets."""
from __future__ import annotations

import re

SDXL_DEFAULT_NEGATIVE = (
    "mutated hands, blurry, bad anatomy, deformed, extra fingers, fused fingers, "
    "poorly drawn face, low quality, watermark, text, logo"
)

VIDEO_TEMPORAL_CUES = (
    "single continuous physical take, stable subject identity, stable room geometry, "
    "natural acceleration and deceleration, no unplanned cuts, no morphing, "
    "no teleportation, endpoint settles cleanly"
)

_TAG_SOUP = {
    "masterpiece",
    "best quality",
    "high quality",
    "ultra quality",
    "absurdres",
    "highres",
    "8k",
    "4k",
    "uhd",
}


def _split_phrases(text: str) -> list[str]:
    raw = re.split(r"[,;\n]+", str(text or ""))
    phrases: list[str] = []
    seen: set[str] = set()
    for item in raw:
        cleaned = re.sub(r"\s+", " ", item).strip(" .")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        phrases.append(cleaned)
    return phrases


def _join_unique(*parts: str) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        for phrase in _split_phrases(part):
            key = phrase.lower()
            if key not in seen:
                seen.add(key)
                out.append(phrase)
    return ", ".join(out)


def _strip_quality_tag_soup(prompt: str) -> str:
    phrases = [
        phrase for phrase in _split_phrases(prompt)
        if phrase.lower() not in _TAG_SOUP
    ]
    return ", ".join(phrases) if phrases else str(prompt or "").strip()


def _format_sdxl(prompt: str, base_negative: str) -> dict:
    phrases = _split_phrases(prompt)
    primary = phrases[0] if phrases else str(prompt or "").strip()
    qualifiers = phrases[1:]
    positive_parts = [primary]
    if qualifiers:
        positive_parts.extend(qualifiers)
    positive_parts.extend([
        "photorealistic",
        "sharp focus",
        "natural lighting",
        "detailed texture",
    ])
    return {
        "target_model": "sdxl",
        "dialect": "comma_tags",
        "prompt": _join_unique(", ".join(positive_parts)),
        "negative_prompt": _join_unique(base_negative, SDXL_DEFAULT_NEGATIVE),
        "metadata": {
            "primary_subject": primary,
            "formatter": "local_agent.prompt_router.format_prompt_for_target",
        },
    }


def _format_flux(prompt: str, base_negative: str) -> dict:
    cleaned = _strip_quality_tag_soup(prompt)
    phrases = _split_phrases(cleaned)
    prose = ". ".join(phrase[0].upper() + phrase[1:] for phrase in phrases if phrase)
    if prose and not prose.endswith("."):
        prose += "."
    return {
        "target_model": "flux",
        "dialect": "natural_language",
        "prompt": prose or cleaned,
        "negative_prompt": "",
        "metadata": {
            "negative_handling": "ignored_by_target",
            "ignored_negative_prompt": base_negative.strip(),
            "formatter": "local_agent.prompt_router.format_prompt_for_target",
        },
    }


def _format_video(prompt: str, base_negative: str, target: str) -> dict:
    try:
        from temporal_physics import (
            camera_is_locked,
            has_specified_motion,
            runtime_inject_temporal_physics,
        )
    except ImportError:
        from local_agent.temporal_physics import (
            camera_is_locked,
            has_specified_motion,
            runtime_inject_temporal_physics,
        )

    text = re.sub(r"\s+", " ", str(prompt or "")).strip()
    first_sentence = re.split(r"(?<=[.!?])\s+", text, maxsplit=1)[0] if text else ""
    subject = first_sentence.strip(" .") or "the subject"
    expanded = runtime_inject_temporal_physics(text, style="backrooms") if text else text
    if camera_is_locked(text):
        camera = "locked or static camera as specified in the prompt, no handheld walking momentum"
    elif has_specified_motion(text):
        camera = "follow the prompt's existing camera move; do not add handheld walking momentum"
    else:
        camera = "handheld tracking with believable physical momentum"
    prompt_out = (
        f"Subject: {subject}. "
        f"Camera motion: {camera}. "
        f"Atmosphere: grounded lighting, consistent environment, coherent motion. "
        f"Temporal stability: {VIDEO_TEMPORAL_CUES}. "
        f"Action: {expanded}"
    )
    return {
        "target_model": target,
        "dialect": "temporal_video",
        "prompt": prompt_out,
        "negative_prompt": _join_unique(
            base_negative,
            "flicker, frame tearing, warped limbs, unstable geometry, visible cuts",
        ),
        "metadata": {
            "subject": subject,
            "formatter": "local_agent.prompt_router.format_prompt_for_target",
        },
    }


def format_prompt_for_target(prompt: str, target_model: str, base_negative: str = "") -> dict:
    """Format ``prompt`` into the requested image/video model dialect."""
    target = str(target_model or "").strip().lower()
    if not target:
        raise ValueError("target_model is required")
    if target in {"sdxl", "xl", "stable-diffusion-xl"}:
        return _format_sdxl(prompt, base_negative)
    if target in {"flux", "flux.1", "flux1"}:
        return _format_flux(prompt, base_negative)
    if target in {"video", "wan", "minimax", "i2v", "t2v"}:
        canonical = "video" if target in {"i2v", "t2v"} else target
        return _format_video(prompt, base_negative, canonical)
    raise ValueError(f"unsupported target_model: {target_model!r}")
