#!/usr/bin/env python3
"""Deterministic pre-screening for operator-curated exemplar candidates.

This module intentionally does not download an embedding model or contact a
vector database.  A candidate can enter the *pending* review queue, never the
active knowledge base, until an operator approves the separate embedding step.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

_MJ_PARAMETER = re.compile(r"(?:^|\s)--(?:ar|v)\b", re.I)


def fingerprint(content: str) -> str:
    return hashlib.sha256(" ".join(str(content).split()).encode("utf8")).hexdigest()


def check_candidate(item: dict, existing_fingerprints: set[str] | None = None) -> dict:
    """Return deterministic validation facts; never mutates the candidate."""
    errors: list[str] = []
    warnings: list[str] = []
    category = str(item.get("category", ""))
    content = str(item.get("content", ""))
    if category not in {"video_prompt", "comfyui_workflow", "screenplay_beat"}:
        errors.append("unsupported category")
    if not content.strip():
        errors.append("content is required")
    if category == "video_prompt":
        if len(content.split()) < 10:
            errors.append("video prompts need at least 10 words")
        if _MJ_PARAMETER.search(content):
            errors.append("Midjourney parameters are not valid H3/ComfyUI prompt content")
    if category == "comfyui_workflow":
        try:
            workflow = json.loads(content)
            nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
            if not isinstance(nodes, list):
                errors.append("workflow JSON must contain a nodes list")
            elif any(not isinstance(node, dict) or not node.get("type") for node in nodes):
                errors.append("each workflow node needs a non-empty type")
            else:
                # Installation verification needs a live local ComfyUI node map.
                # Do not guess it from a filename and accidentally certify a bad
                # workflow; this warning blocks automatic activation.
                warnings.append("node availability requires local ComfyUI verification at approval")
        except json.JSONDecodeError:
            errors.append("workflow content is not valid JSON")
    digest = fingerprint(content)
    if existing_fingerprints and digest in existing_fingerprints:
        errors.append("exact duplicate of an existing staged or approved candidate")
    semantic: dict = {"available": False, "reason": "not checked"}
    if not errors and category in {"video_prompt", "comfyui_workflow", "screenplay_beat"}:
        try:
            import exemplar_embeddings
            semantic = exemplar_embeddings.semantic_duplicate(category, content)
            if semantic.get("duplicate"):
                errors.append("semantic duplicate of approved exemplar "
                              f"{semantic.get('id')} (similarity {semantic.get('similarity')})")
        except Exception as exc:
            # A semantic check failing never turns into an automatic approval.
            # Preserve the candidate for explicit review and make the missing
            # check visible to the operator.
            semantic = {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
            warnings.append("semantic duplicate check unavailable; approval requires review")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "fingerprint": digest, "semantic_dedup": semantic}
