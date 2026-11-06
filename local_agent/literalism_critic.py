#!/usr/bin/env python3
"""PromptSurgeon — Subject-Object Literalism critic (scaffolding).

Detects when a perspective/tool word in the prompt (POV, drone, camcorder, …)
is rendered as a visible prop in the VLM description, then revises prompts.

Dry-run / stage only while GPU batches are live: do not call Ollama from
orchestration paths unless the operator explicitly enables a critic LM later.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

try:
    import dspy  # optional at import time; heuristic path works without it
except Exception:  # pragma: no cover
    dspy = None  # type: ignore


# Perspective / capture-device tokens that belong in CAMERA INTENT, not as props.
PERSPECTIVE_LEXICON: dict[str, tuple[str, ...]] = {
    "pov": ("pov", "point of view", "first-person", "first person", "fpv"),
    "drone": ("drone", "quadcopter", "uav", "aerial drone"),
    "camcorder": ("camcorder", "handycam", "vhs camera", "home video camera"),
    "camera": ("camera", "dslr", "mirrorless body", "film camera"),
    "gopro": ("gopro", "action cam", "action camera"),
    "phone": ("smartphone", "iphone", "phone camera", "holding a phone"),
    "tripod": ("tripod", "on a tripod"),
    "gimbal": ("gimbal", "steadicam rig"),
}

# Phrases that mean the VLM saw the gear as a subject/object in frame.
VISIBLE_PROP_CUES: tuple[str, ...] = (
    "holding a camera",
    "holding the camera",
    "camera in the frame",
    "camera visible",
    "drone in the sky",
    "drone flying into view",
    "sees a drone",
    "sees the camera",
    "camcorder in",
    "person with a camera",
    "operator holding",
    "tripod standing",
    "phone held up",
    "filming himself with",
    "filming herself with",
)


@dataclass
class LiteralismVerdict:
    literalism_detected: bool
    revised_positive_prompt: str
    revised_negative_prompt: str
    flagged_terms: list[str]
    rationale: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "literalism_detected": bool(self.literalism_detected),
            "revised_positive_prompt": self.revised_positive_prompt,
            "revised_negative_prompt": self.revised_negative_prompt,
            "flagged_terms": list(self.flagged_terms),
            "rationale": self.rationale,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _intent_terms(positive: str) -> list[str]:
    blob = _norm(positive)
    hits: list[str] = []
    for canonical, variants in PERSPECTIVE_LEXICON.items():
        if any(v in blob for v in variants) or canonical in blob.split():
            hits.append(canonical)
    # de-dupe preserve order
    out: list[str] = []
    for h in hits:
        if h not in out:
            out.append(h)
    return out


def _vlm_shows_prop(vlm_raw: str, term: str) -> bool:
    blob = _norm(vlm_raw)
    if not blob:
        return False
    variants = PERSPECTIVE_LEXICON.get(term, (term,))
    cue_hit = any(c in blob for c in VISIBLE_PROP_CUES)
    term_hit = any(v in blob for v in variants)
    # Literalism: VLM describes the capture device as a seen object.
    if cue_hit and term_hit:
        return True
    # Strong patterns: "a <device> is visible/in frame/held"
    for v in variants:
        if re.search(
            rf"\b(a|the|an)\s+{re.escape(v)}\b.*\b(visible|in (the )?frame|held|holding|appears|shown)\b",
            blob,
        ):
            return True
        if re.search(
            rf"\b(holding|gripping|carrying|operating)\s+(a|the|an)\s+{re.escape(v)}\b",
            blob,
        ):
            return True
    return False


def _strip_equipment_words(positive: str, terms: list[str]) -> str:
    text = positive or ""
    for term in terms:
        variants = sorted(PERSPECTIVE_LEXICON.get(term, (term,)), key=len, reverse=True)
        for v in variants:
            text = re.sub(rf"\b{re.escape(v)}\b", " ", text, flags=re.IGNORECASE)
    # Prefer perspective phrasing without naming the prop.
    replacements = {
        "pov": "first-person viewpoint",
        "drone": "high aerial moving viewpoint",
        "camcorder": "handheld documentary viewpoint",
        "camera": "cinematic viewpoint",
        "gopro": "helmet-mounted action viewpoint",
        "phone": "handheld viewpoint",
        "tripod": "locked-off stable viewpoint",
        "gimbal": "smooth stabilized tracking viewpoint",
    }
    # If stripping emptied the camera clause, append a clean intent phrase once.
    lowered = _norm(text)
    for term in terms:
        phrase = replacements.get(term)
        if phrase and phrase.lower() not in lowered:
            text = (text.rstrip(",; ") + ", " + phrase).strip(",; ")
            lowered = _norm(text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+,", ",", text)
    return text.strip(" ,;")


def _append_negatives(negative: str, terms: list[str]) -> str:
    ban_map = {
        "pov": "camera body in frame, person holding a camera",
        "drone": "drone aircraft visible, quadcopter in shot, UAV propellers",
        "camcorder": "camcorder prop visible, handycam in frame",
        "camera": "camera equipment visible, DSLR in frame, photographer holding camera",
        "gopro": "GoPro device visible, action camera in frame",
        "phone": "smartphone visible in frame, person filming with phone",
        "tripod": "tripod visible, camera on tripod in shot",
        "gimbal": "gimbal rig visible, steadicam vest in frame",
    }
    existing = negative or ""
    extras: list[str] = []
    low = _norm(existing)
    for term in terms:
        phrase = ban_map.get(term, f"{term} visible in frame")
        if _norm(phrase) not in low:
            extras.append(phrase)
    if not extras:
        return existing.strip()
    if existing.strip():
        return existing.rstrip(",; ") + ", " + ", ".join(extras)
    return ", ".join(extras)


def critique_literalism_heuristic(
    original_positive_prompt: str,
    original_negative_prompt: str,
    vlm_raw_description: str,
) -> LiteralismVerdict:
    """CPU-only heuristic critic (no LM / no VRAM)."""
    intent = _intent_terms(original_positive_prompt)
    flagged = [t for t in intent if _vlm_shows_prop(vlm_raw_description, t)]
    if not flagged:
        return LiteralismVerdict(
            literalism_detected=False,
            revised_positive_prompt=original_positive_prompt,
            revised_negative_prompt=original_negative_prompt,
            flagged_terms=[],
            rationale="No subject-object literalism: perspective terms are not described as visible props.",
        )
    revised_pos = _strip_equipment_words(original_positive_prompt, flagged)
    revised_neg = _append_negatives(original_negative_prompt, flagged)
    return LiteralismVerdict(
        literalism_detected=True,
        revised_positive_prompt=revised_pos,
        revised_negative_prompt=revised_neg,
        flagged_terms=flagged,
        rationale=(
            "Prompt asks for capture perspective "
            f"{flagged}, but VLM describes that equipment as a visible object in scene."
        ),
    )


if dspy is not None:

    class LiteralismCritique(dspy.Signature):
        """Detect subject-object literalism and revise prompts."""

        original_positive_prompt: str = dspy.InputField(desc="Positive prompt used for generation")
        original_negative_prompt: str = dspy.InputField(desc="Negative prompt used for generation")
        vlm_raw_description: str = dspy.InputField(
            desc="Raw VLM caption / rationale of what is visually present"
        )
        literalism_detected: bool = dspy.OutputField(
            desc=(
                "True if the prompt requested a viewpoint/tool (POV, drone, camcorder, …) "
                "but the VLM describes seeing that physical equipment as a subject/object"
            )
        )
        revised_positive_prompt: str = dspy.OutputField(
            desc="Positive prompt with equipment nouns stripped; keep viewpoint intent in words"
        )
        revised_negative_prompt: str = dspy.OutputField(
            desc="Negative prompt with literal equipment objects appended"
        )
        rationale: str = dspy.OutputField(desc="Short explanation of the decision")

    class PromptSurgeon(dspy.Module):
        """LM-backed critic. Prefer heuristic path under GPU lock."""

        def __init__(self) -> None:
            super().__init__()
            self.critique = dspy.ChainOfThought(LiteralismCritique)

        def forward(
            self,
            original_positive_prompt: str,
            original_negative_prompt: str,
            vlm_raw_description: str,
        ):
            return self.critique(
                original_positive_prompt=original_positive_prompt,
                original_negative_prompt=original_negative_prompt,
                vlm_raw_description=vlm_raw_description,
            )


def critique_literalism(
    original_positive_prompt: str,
    original_negative_prompt: str,
    vlm_raw_description: str,
    *,
    use_lm: bool = False,
) -> dict[str, Any]:
    """Public entrypoint used by the staged orchestrator patch.

    Default ``use_lm=False`` keeps this CPU-only (safe under GPU saturation).
    """
    if use_lm and dspy is not None:
        surgeon = PromptSurgeon()
        pred = surgeon(
            original_positive_prompt=original_positive_prompt,
            original_negative_prompt=original_negative_prompt,
            vlm_raw_description=vlm_raw_description,
        )
        detected = bool(getattr(pred, "literalism_detected", False))
        return {
            "literalism_detected": detected,
            "revised_positive_prompt": str(
                getattr(pred, "revised_positive_prompt", original_positive_prompt) or original_positive_prompt
            ),
            "revised_negative_prompt": str(
                getattr(pred, "revised_negative_prompt", original_negative_prompt) or original_negative_prompt
            ),
            "flagged_terms": [],
            "rationale": str(getattr(pred, "rationale", "") or ""),
        }
    return critique_literalism_heuristic(
        original_positive_prompt,
        original_negative_prompt,
        vlm_raw_description,
    ).as_dict()