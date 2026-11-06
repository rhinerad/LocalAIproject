#!/usr/bin/env python3
"""Safe structural normalisation for review-only MiniMax H3 exemplars.

The canonical H3 validator rejects ``[0-1 s]`` timing brackets.  This module
therefore preserves timing as prose and uses ``[Shot N]`` only for a real cut.
It does not claim that an arbitrary internet prompt is production-ready.
"""
from __future__ import annotations

import re

from validate_h3_prompt import SECTIONS, validate

_ZERO_TAG = re.compile(r"<(Picture|Subject|Audio)\s+0>")
_TIME_BRACKET = re.compile(r"\[\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*s?\s*\]")


def _tags_one_based(text: str) -> str:
    return _ZERO_TAG.sub(lambda match: f"<{match.group(1)} 1>", text)


def _timing_prose(text: str) -> str:
    return _TIME_BRACKET.sub(lambda match: f"from {match.group(1)} to {match.group(2)} seconds", text)


def normalize(content: str) -> dict:
    """Return transformed text and a validator report without writing files."""
    original = str(content or "").strip()
    transformed = _timing_prose(_tags_one_based(original))
    has_sections = all(re.search(rf"^{re.escape(section)}\s*$", transformed, re.M)
                       for section in SECTIONS)
    if not has_sections:
        # This is a review scaffold, not fabricated scene detail.  It keeps the
        # candidate's words intact while making the H3 grammar inspectable.
        transformed = "\n\n".join((
            "subject_definitions:\n<Subject 1>: The primary subject described in the reviewed source.\n<Picture 1>: The reviewed visual reference.",
            "summary:\nA single continuous take based only on the reviewed source description.",
            "retention_analysis:\n<Picture 1> reference for visible appearance and composition.",
            f"detailed_description:\n[Shot 1] {transformed}",
            "overall_soundscape:\nUse only sound explicitly described in the reviewed source.",
            "non_diegetic_music:\nN/A",
        ))
    report = validate(transformed, "<staged exemplar>").as_dict()
    return {"original": original, "normalized": transformed, "changed": transformed != original,
            "valid_h3": report["valid"], "report": report,
            "timing_policy": "timing retained as prose; bracketed seconds are invalid H3 grammar"}
