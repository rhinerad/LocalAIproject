#!/usr/bin/env python3
"""Render reviewed operating memory by explicit scope, never keyword deletion."""
from __future__ import annotations

from pathlib import Path

PROJECT_HEADING = "## Project policy"


def render(path: Path, *, include_project: bool) -> str:
    """Return reviewed general/machine sections, plus project section if scoped.

    Old unsectioned files are treated as a general section to avoid silently
    dropping policy during a migration.  A project section is an all-or-nothing
    block; no line-level term filter is used.
    """
    try:
        text = path.read_text(encoding="utf8").strip()
    except OSError:
        return ""
    if not text:
        return ""
    if PROJECT_HEADING not in text:
        return text
    before, project = text.split(PROJECT_HEADING, 1)
    return text if include_project else before.rstrip()
