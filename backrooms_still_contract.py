#!/usr/bin/env python3
"""Still / temporal boundary contract helpers for Backrooms production.

Ref2VA image refs alone are NOT temporal first/last proof. Animation must be
blocked until stills are approved under an explicit stills_approved map.
"""
from __future__ import annotations

from typing import Any, Mapping


class StillContractError(RuntimeError):
    pass


CONTRACT_DOC = (
    "references.start and references.last must carry approved asset ids "
    "(and optional sha). video_requires_still_review blocks animation when "
    "stills are not approved. Generic Ref2VA image refs alone do not prove "
    "temporal first/last frame placement on the editorial timeline."
)


def require_still_reference_ids(clip: Mapping[str, Any]) -> dict[str, Any]:
    """Require references.start / references.last asset ids (+ optional sha)."""
    refs = clip.get("references") or {}
    if not isinstance(refs, Mapping):
        raise StillContractError(f"{clip.get('id')}: references missing or not a mapping")
    start = refs.get("start")
    last = refs.get("last")
    if not start:
        raise StillContractError(f"{clip.get('id')}: references.start asset id required")
    if not last:
        raise StillContractError(f"{clip.get('id')}: references.last asset id required")
    return {
        "start": start,
        "last": last,
        "start_sha": refs.get("start_sha") or refs.get("start_sha256"),
        "last_sha": refs.get("last_sha") or refs.get("last_sha256"),
        "video_requires_still_review": bool(
            refs.get("video_requires_still_review")
            or clip.get("video_requires_still_review")
        ),
        "contract_doc": CONTRACT_DOC,
    }


def video_requires_still_review(
    clip: Mapping[str, Any],
    stills_approved: Mapping[str, Any] | None = None,
) -> bool:
    """True when animation must wait for still approval."""
    refs = clip.get("references") or {}
    flagged = False
    if isinstance(refs, Mapping):
        flagged = bool(refs.get("video_requires_still_review"))
    flagged = flagged or bool(clip.get("video_requires_still_review"))
    if not flagged:
        return False
    approved = stills_approved or {}
    cid = str(clip.get("id") or "")
    start_id = None
    last_id = None
    if isinstance(refs, Mapping):
        start_id = refs.get("start")
        last_id = refs.get("last")
    start_ok = bool(approved.get(str(start_id))) or bool(approved.get(f"{cid}_start"))
    last_ok = bool(approved.get(str(last_id))) or bool(approved.get(f"{cid}_last"))
    # Also allow per-clip blanket approval key.
    if approved.get(cid) is True:
        return False
    return not (start_ok and last_ok)


def assert_stills_approved_for_animation(
    clip: Mapping[str, Any],
    stills_approved: Mapping[str, Any] | None = None,
) -> None:
    """Block animation if still review is required and not satisfied."""
    require_still_reference_ids(clip)
    if video_requires_still_review(clip, stills_approved):
        raise StillContractError(
            f"{clip.get('id')}: stills not approved — animation blocked "
            f"(Ref2VA image refs alone ≠ temporal first/last proof). {CONTRACT_DOC}"
        )
