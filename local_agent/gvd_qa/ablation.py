"""Prompt-keyword ablation without ComfyUI-PromptTester."""
from __future__ import annotations

import re
from typing import Iterable

_STOP = frozenset({
    "a", "an", "the", "and", "or", "of", "in", "on", "at", "to", "with", "from",
    "for", "by", "as", "is", "are", "no", "not", "very", "highly", "shot",
    "image", "photo", "video", "frame", "still",
})
_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9'-]{2,}")


def tokenize_prompt(prompt: str) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.finditer((prompt or "").lower()):
        token = match.group(0).replace("_", " ").strip()
        if token in _STOP or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def ignored_keywords(prompt: str, tags: Iterable[str], *, min_token_len: int = 4) -> list[str]:
    """Keywords present in the prompt that WD14 / tags did not echo."""
    tag_blob = " ".join(str(t).lower().replace("_", " ") for t in tags)
    ignored: list[str] = []
    for token in tokenize_prompt(prompt):
        if len(token) < min_token_len:
            continue
        if token not in tag_blob:
            ignored.append(token)
    return ignored
