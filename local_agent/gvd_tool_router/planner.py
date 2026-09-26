"""Planner: narrative intent → typed ShotManifest. Cannot invent node types."""
from __future__ import annotations

import json
import re
from typing import Any

from .schema import ShotManifest, shot_from_dict

_CONTINUOUS = re.compile(r"\b(no cuts?|unbroken|continuous take|one take|one cut)\b", re.I)
_MORPH = re.compile(r"\b(morph|dream sequence|prompt travel|transform into)\b", re.I)
_IDENTITY = re.compile(r"\b(character|wardrobe|named|cast|identity|hero|she|he)\b", re.I)
_DIALOGUE = re.compile(r"\b(says?|dialogue|speaks?|line:|lip-?sync)\b", re.I)
_REPAIR = re.compile(r"\b(inpaint|remove the|repair|erase)\b", re.I)
_ACTION = re.compile(r"\b(b-?roll|establishing|action|draft)\b", re.I)
# Operator engine policy (2026-09-26b): MiniMax is the default; Wan only when
# the operator's own words name it. A bare "wan" is not a request (the
# English word exists); a verb of choice next to it is. Negations win.
_WAN_REQUEST = re.compile(
    r"\b(?:use|using|try|with|on|via|through|prefer|force|pick|choose|select|run"
    r"|render(?:\s+(?:it|this|this one|that))?(?:\s+(?:with|on|in|through|using))?"
    r"|switch(?:\s+over)?\s+to|go\s+with|fall\s+back\s+to)"
    r"\s+wan(?:\s?2(?:\.\d)?)?\b"
    r"|\bwan(?:\s?2(?:\.\d)?)?\s+(?:for\s+this(?:\s+one)?|instead|please|this\s+time|only)\b",
    re.I,
)
_WAN_NEGATED = re.compile(
    r"\b(?:not|no|never|don'?t|do\s+not|avoid|without|skip|instead\s+of)\s+"
    r"(?:use\s+|using\s+|try\s+|trying\s+)?wan\b",
    re.I,
)


def requested_engine_from_text(text: str) -> tuple[str | None, str | None]:
    """("wan", matched span) when the operator explicitly asks for Wan, else
    (None, None). MiniMax is the default and needs no words."""
    if _WAN_NEGATED.search(text):
        return None, None
    hit = _WAN_REQUEST.search(text)
    if not hit:
        return None, None
    return "wan", hit.group(0)


def plan_shot(
    text: str,
    *,
    shot_id: str = "S01",
    width: int = 1280,
    height: int = 720,
    duration_s: float = 4.0,
    user_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Deterministic classifier. User-specified fields always win."""
    evidence: dict[str, str] = {}
    confidence: dict[str, float] = {}
    mode = "independent"
    hard: set[str] = set()
    if _CONTINUOUS.search(text):
        mode = "continuous"
        evidence["continuous"] = _CONTINUOUS.search(text).group(0)
        confidence["continuous"] = 0.8
    if _MORPH.search(text):
        mode = "morph"
        evidence["morph"] = _MORPH.search(text).group(0)
        confidence["morph"] = 0.75
    if _IDENTITY.search(text) and mode != "morph":
        if mode == "continuous":
            hard.update({"identity_reference", "video_continuation"})
        else:
            mode = "identity"
        evidence["identity"] = _IDENTITY.search(text).group(0)
        confidence["identity"] = 0.7
    if _DIALOGUE.search(text):
        hard.update({"tts", "lipsync"})
        evidence["dialogue"] = _DIALOGUE.search(text).group(0)
        confidence["dialogue"] = 0.8
    if _REPAIR.search(text):
        hard.add("video_inpainting")
        evidence["repair"] = _REPAIR.search(text).group(0)
    if _ACTION.search(text) and mode == "independent":
        evidence["fast"] = _ACTION.search(text).group(0)
        confidence["fast"] = 0.6
    if not evidence:
        return {
            "status": "needs_manifest_review",
            "reason_codes": ["NEEDS_MANIFEST_REVIEW"],
            "note": "unknown interpretation; refusing to pick the fastest tool",
        }
    # Naming an engine is not a shot interpretation, so it is read only after
    # the review check above; it never rescues an otherwise unreadable request.
    requested_engine, engine_span = requested_engine_from_text(text)
    if requested_engine:
        evidence["requested_engine"] = engine_span or ""
        confidence["requested_engine"] = 0.9
    payload = {
        "shot_id": shot_id,
        "script_intent": text.strip(),
        "camera_motion": "unspecified",
        "character_state": [],
        "continuity_mode": mode,
        "duration_s": duration_s,
        "width": width,
        "height": height,
        "fps_num": 24,
        "fps_den": 1,
        "hard_requirements": sorted(hard),
        "priorities": {},
        "inferred_confidence": confidence,
        "evidence_spans": evidence,
        "requested_engine": requested_engine,
    }
    if user_manifest:
        for key, value in user_manifest.items():
            if value is not None and key != "inferred_confidence":
                payload[key] = value
    try:
        manifest = shot_from_dict(payload)
    except Exception as exc:
        return {"status": "needs_manifest_review", "reason_codes": [type(exc).__name__]}
    return {
        "status": "planned",
        "manifest": payload,
        "note": "planner emits constraints only; it cannot name Comfy node classes",
        "shot_id": manifest.shot_id,
        "continuity_mode": manifest.continuity_mode,
        "requested_engine": manifest.requested_engine,
    }
