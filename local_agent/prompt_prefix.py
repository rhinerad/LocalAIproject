#!/usr/bin/env python3
"""Byte-stable prompt sections for efficient local inference reuse.

Ollama/llama.cpp can reuse a repeated prefix only when its bytes and ordering
match. These pure, cached renderers keep static policy and recalled-memory
sections deterministic while `agent.py` remains responsible for selecting their
scope and live task evidence.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=128)
def render_static_prefix(rules: str, operating: str, learned: str) -> str:
    return rules + operating + learned


@lru_cache(maxsize=128)
def render_memory_prefix(memory_block: str) -> str:
    return (f"\n\n# What I know about this operator\n\n{memory_block}"
            if memory_block else "")


@lru_cache(maxsize=128)
def render_project_prefix(project_text: str) -> str:
    if not project_text:
        return ""
    return ("\n\n# Equal Shares specialist reference\n\n"
            "The following handbook applies only to explicit Equal Shares or "
            "MiniMax H3 work, an Equal Shares clip identifier, or an Equal "
            "Shares project file/path. It must not change ordinary assistant "
            "behavior.\n\n" + project_text)
