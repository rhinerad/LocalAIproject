#!/usr/bin/env python3
"""GVD core helpers + DSPy Template-Driven Prompt Decomposition.

Pure timing helpers (h3_generation_frames) are importable without dspy.
The DSPy module section requires dspy when GeneralVideoDirector is used.
Scaffolding only: do not import/run DSPy while a GPU batch owns the card.

P1-C: planner requests quality_tier / motion_complexity only.
Sampling (steps/scheduler/sampler/denoise/canvas) comes from backend_profiles.
"""
from __future__ import annotations

from typing import Any


def h3_generation_frames(required_frames: int) -> int:
    """Map editorial frame count to a validated MiniMax H3 generation length.

    H3 lengths must be congruent to 5 mod 17 and stay within ~124–362.
    Short editorial spans render at >=124 then trim; oversize requests must
    be split into multiple render segments.
    """
    if isinstance(required_frames, bool) or not isinstance(required_frames, int) or required_frames < 1:
        raise ValueError("positive integer frame count required")
    n = max(124, required_frames)
    n += (5 - n % 17) % 17
    if n > 362:
        raise ValueError("Split into multiple render segments")
    return n


def editorial_vs_generation_frames(editorial_frames: int) -> tuple[int, int]:
    """Return (editorial_frames, generation_frames) without collapsing them."""
    editorial = int(editorial_frames)
    if editorial < 1:
        raise ValueError("editorial_frames must be >= 1")
    return editorial, h3_generation_frames(editorial)


# Creative planner tiers — NOT sampler knobs
QUALITY_TIERS = ("draft", "standard", "high", "hero")
MOTION_COMPLEXITIES = ("static", "subtle", "moderate", "complex")

# Legacy Wan/FLUX ranges kept only for explicit non-H3 backends (documentation)
CFG_SCALE_RANGE = (1.0, 8.0)
DENOISE_RANGE = (0.35, 1.0)
STEPS_RANGE = (16, 40)


def normalize_planner_creative(
    *,
    quality_tier: str | None = None,
    motion_complexity: str | None = None,
    backend_profile: str = "h3_distilled",
) -> dict[str, Any]:
    """Normalize planner creative request; never invent CFG/steps for H3."""
    tier = (quality_tier or "standard").strip().lower()
    motion = (motion_complexity or "moderate").strip().lower()
    if tier not in QUALITY_TIERS:
        raise ValueError(f"quality_tier must be one of {QUALITY_TIERS}")
    if motion not in MOTION_COMPLEXITIES:
        raise ValueError(f"motion_complexity must be one of {MOTION_COMPLEXITIES}")
    try:
        from backend_profiles import planner_request_to_hparams
        hp = planner_request_to_hparams(
            backend_profile=backend_profile,
            quality_tier=tier,
            motion_complexity=motion,
        )
    except ImportError:
        # Minimal offline fallback matching H3 distilled reference
        hp = {
            "step_count": {"draft": 12, "standard": 20, "high": 24, "hero": 28}[tier],
            "denoise": 1.0,
            "scheduler": "simple",
            "sampler_name": "res_multistep",
            "backend_profile": backend_profile,
            "quality_tier": tier,
            "motion_complexity": motion,
            "uses_cfg": False,
            "cfg_scale": None,
        }
    return {
        "quality_tier": tier,
        "motion_complexity": motion,
        "backend_profile": backend_profile,
        "hparams": hp,
    }


def _load_dspy_module():
    """Lazy-load DSPy director so pure helpers stay offline-importable."""
    import dspy

    class VideoPromptTemplate(dspy.Signature):
        """Decompose a raw narrative into GVD template fields, then compile one ComfyUI prompt.

        Do NOT invent sampler knobs (CFG / steps / denoise). Those come from
        deterministic backend profiles. Request quality_tier and motion_complexity only.
        """

        raw_narrative: str = dspy.InputField(
            desc="Operator's raw story or shot request. Ground truth for what may appear."
        )
        subject_and_action: str = dspy.OutputField(
            desc=(
                "Primary subject(s) and what they are doing. "
                "NEVER invent elements like fluorescent lights or damp carpets unless "
                "explicitly requested in the raw_narrative."
            )
        )
        environment: str = dspy.OutputField(
            desc=(
                "Setting / location / background only. "
                "NEVER invent liminal Backrooms, fluorescent tubes, or damp carpets unless "
                "explicitly requested in the raw_narrative."
            )
        )
        camera_and_motion: str = dspy.OutputField(
            desc=(
                "Camera rig, lens feel, and motion path for the clip. "
                "NEVER invent elements like fluorescent lights or damp carpets unless "
                "explicitly requested in the raw_narrative."
            )
        )
        lighting_and_style: str = dspy.OutputField(
            desc=(
                "Lighting, palette, and visual style. "
                "NEVER invent fluorescent lights, VHS Backrooms grit, or damp carpets unless "
                "explicitly requested in the raw_narrative."
            )
        )
        final_comfyui_prompt: str = dspy.OutputField(
            desc=(
                "Single dense positive prompt string compiled ONLY from the decomposed fields "
                "and raw_narrative. No aesthetic bleed from unrelated domains."
            )
        )
        quality_tier: str = dspy.OutputField(
            desc="One of: draft | standard | high | hero. Creative quality request only — not sampler steps."
        )
        motion_complexity: str = dspy.OutputField(
            desc="One of: static | subtle | moderate | complex. Motion complexity request only — not CFG."
        )

    class GeneralVideoDirector(dspy.Module):
        """Template-driven GVD student: CoT over VideoPromptTemplate."""

        def __init__(self) -> None:
            super().__init__()
            self.decompose = dspy.ChainOfThought(VideoPromptTemplate)

        def forward(self, raw_narrative: str):
            return self.decompose(raw_narrative=raw_narrative)

    return VideoPromptTemplate, GeneralVideoDirector


# Back-compat: define names when dspy is available; otherwise leave callables that raise.
try:
    VideoPromptTemplate, GeneralVideoDirector = _load_dspy_module()
except Exception:  # ModuleNotFoundError or similar
    class VideoPromptTemplate:  # type: ignore
        def __init__(self, *a, **k):
            raise ModuleNotFoundError("dspy is required for VideoPromptTemplate")

    class GeneralVideoDirector:  # type: ignore
        def __init__(self, *a, **k):
            raise ModuleNotFoundError("dspy is required for GeneralVideoDirector")
