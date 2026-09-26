"""Duplicate-generation detection for semantic still QA.

Flags near-identical outputs by caption token overlap and a perceptual
dhash fingerprint against prior frames and the requested prompt. Callers
record the evidence and diagnose the cause before any bounded retry.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only in stripped envs
    Image = None  # type: ignore[assignment]
    _PIL_AVAILABLE = False

from .constants import DUP_CAPTION_OVERLAP_MAX, DUP_DHASH_MAX_DISTANCE


def caption_tokens(text: str) -> set[str]:
    return {
        token
        for token in " ".join(str(text).lower().replace("_", " ").split()).split()
        if len(token) > 2 or token.isdigit()
    }


def caption_overlap(a: str, b: str) -> float:
    """Token Jaccard similarity in [0, 1]."""
    ta, tb = caption_tokens(a), caption_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _dhash(image: Any) -> int:
    im = image.convert("L").resize((9, 8))
    try:
        pixels = list(im.get_flattened_data())  # Pillow >= 12
    except AttributeError:  # pragma: no cover - older Pillow
        pixels = list(im.getdata())
    bits = 0
    for y in range(8):
        row = y * 9
        for x in range(8):
            bits = (bits << 1) | (1 if pixels[row + x] > pixels[row + x + 1] else 0)
    return bits


def dhash_bytes(image: bytes) -> int | None:
    if not _PIL_AVAILABLE:
        return None
    try:
        with Image.open(BytesIO(image)) as im:
            return _dhash(im)
    except Exception:
        return None


def dhash_file(path: str | Path) -> int | None:
    if not _PIL_AVAILABLE:
        return None
    try:
        with Image.open(Path(path)) as im:
            return _dhash(im)
    except Exception:
        return None


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def detect_duplicates(
    *,
    candidate_image: bytes | None = None,
    candidate_path: str | Path | None = None,
    candidate_caption: str = "",
    prior: Iterable[tuple[str, str | Path | None]] = (),
    caption_max: float = DUP_CAPTION_OVERLAP_MAX,
    dhash_max: int = DUP_DHASH_MAX_DISTANCE,
) -> dict[str, Any]:
    """Compare a candidate still against prior (caption, image) pairs.

    Returns {"duplicate": bool, "reasons": [...], "evidence": [...]}.
    An empty reasons list means no duplicate was flagged.
    """
    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []
    candidate_hash: int | None = None
    if candidate_image is not None:
        candidate_hash = dhash_bytes(candidate_image)
    elif candidate_path is not None:
        candidate_hash = dhash_file(candidate_path)
    for prior_caption, prior_image in prior:
        overlap = caption_overlap(candidate_caption, prior_caption)
        item: dict[str, Any] = {"caption_overlap": round(overlap, 4)}
        if prior_image is None:
            prior_hash = None
        elif isinstance(prior_image, (str, Path)):
            prior_hash = dhash_file(prior_image)
        else:
            prior_hash = dhash_bytes(prior_image)
        if candidate_hash is not None and prior_hash is not None:
            distance = hamming(candidate_hash, prior_hash)
            item["dhash_distance"] = distance
            if overlap >= caption_max and distance <= dhash_max:
                reasons.append("duplicate_caption_and_fingerprint")
                item["verdict"] = "duplicate"
            else:
                item["verdict"] = "distinct"
        elif overlap >= caption_max:
            reasons.append("duplicate_caption")
            item["verdict"] = "duplicate_caption"
        else:
            item["verdict"] = "distinct"
        evidence.append(item)
    return {
        "duplicate": bool(reasons),
        "reasons": list(dict.fromkeys(reasons)),
        "evidence": evidence,
    }
