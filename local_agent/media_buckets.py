"""Reusable latent-size bucket resolver for local media generation."""
from __future__ import annotations

import math
from typing import Union

AspectInput = Union[str, float, int]

_STANDARD_ASPECTS = {
    "1:1": 1.0,
    "16:9": 16.0 / 9.0,
    "9:16": 9.0 / 16.0,
    "4:3": 4.0 / 3.0,
    "3:2": 3.0 / 2.0,
    "21:9": 21.0 / 9.0,
}


def _parse_aspect(target_aspect: AspectInput) -> float:
    if isinstance(target_aspect, (int, float)):
        ratio = float(target_aspect)
    else:
        text = str(target_aspect).strip().lower()
        if text in _STANDARD_ASPECTS:
            ratio = _STANDARD_ASPECTS[text]
        elif ":" in text:
            left, right = text.split(":", 1)
            ratio = float(left.strip()) / float(right.strip())
        else:
            ratio = float(text)
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError(f"target_aspect must be a positive finite ratio, got {target_aspect!r}")
    return ratio


def _snap(value: float, multiple_of: int) -> int:
    return max(multiple_of, int(round(value / multiple_of)) * multiple_of)


def resolve_latent_bucket(
    target_aspect: AspectInput,
    target_megapixels: float = 1.0,
    multiple_of: int = 64,
) -> tuple[int, int]:
    """Return a width/height bucket near the requested aspect and pixel budget.

    ``target_megapixels=1.0`` uses the SDXL/FLUX-friendly 1024x1024 budget
    (1,048,576 pixels), not the decimal 1,000,000 pixels.
    """
    if multiple_of <= 0:
        raise ValueError("multiple_of must be positive")
    if target_megapixels <= 0 or not math.isfinite(float(target_megapixels)):
        raise ValueError("target_megapixels must be a positive finite number")

    ratio = _parse_aspect(target_aspect)
    target_pixels = float(target_megapixels) * 1024.0 * 1024.0
    ideal_height = math.sqrt(target_pixels / ratio)
    ideal_width = ideal_height * ratio

    width_base = _snap(ideal_width, multiple_of)
    height_base = _snap(ideal_height, multiple_of)

    candidates: set[tuple[int, int]] = set()
    for width_steps in range(-4, 5):
        for height_steps in range(-4, 5):
            width = width_base + width_steps * multiple_of
            height = height_base + height_steps * multiple_of
            if width >= multiple_of and height >= multiple_of:
                candidates.add((width, height))

    def score(size: tuple[int, int]) -> tuple[float, float, int]:
        width, height = size
        pixel_error = abs((width * height) - target_pixels) / target_pixels
        aspect_error = abs((width / height) - ratio) / ratio
        area = width * height
        return (pixel_error + aspect_error * 0.25, aspect_error, area)

    width, height = min(candidates, key=score)
    if width % multiple_of or height % multiple_of:
        raise AssertionError("resolved bucket is not aligned to requested multiple")
    return int(width), int(height)
