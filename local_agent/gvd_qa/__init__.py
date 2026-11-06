"""GVD still/video QA helpers.

The blueprint runner is the repo-root module `gvd_qa.py`
(`generate_until_accepted`, `accepted_i2v_image`). This package holds
graph helpers, review-only Comfy adapters, and whitelist tools.

Do not copy `comfy_adapters.py` into Rockernow custom_nodes without a
promotion receipt.
"""
from __future__ import annotations

from .ablation import ignored_keywords, tokenize_prompt
from .evaluate import evaluate_artifact
from .graph import attach_wd14_tagger, find_image_output_nodes
from .loop import next_seed, run_qa_loop
from .parse import parse_verifier_outputs
from .vram_phases import PHASE_FLUSH, PHASE_GENERATE, PHASE_VALIDATE, run_phase

__all__ = [
    "PHASE_FLUSH",
    "PHASE_GENERATE",
    "PHASE_VALIDATE",
    "attach_wd14_tagger",
    "evaluate_artifact",
    "find_image_output_nodes",
    "ignored_keywords",
    "next_seed",
    "parse_verifier_outputs",
    "run_phase",
    "run_qa_loop",
    "tokenize_prompt",
]
