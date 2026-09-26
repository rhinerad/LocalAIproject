#!/usr/bin/env python3
"""Deterministic backend sampling profiles (P1-C).

Planner / GVD may request quality_tier and motion_complexity only.
Backend profiles choose steps / scheduler / sampler / denoise / canvas.
Never invent Wan/FLUX CFG + 16–40 steps for distilled H3.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

QUALITY_TIERS = frozenset({"draft", "standard", "high", "hero"})
MOTION_COMPLEXITIES = frozenset({"static", "subtle", "moderate", "complex"})

# Distilled MiniMax H3 (matches ref_outputs/h3_i2v_reference.api.json + bind_base_h3)
H3_DISTILLED: dict[str, Any] = {
    "profile_id": "h3_distilled",
    "family": "minimax_h3",
    "sampler_name": "res_multistep",
    "scheduler": "simple",
    "steps": 20,
    "denoise": 1.0,
    # Distilled H3 path does not use CFG guidance the way Wan/FLUX KSampler does.
    "cfg_scale": None,
    "uses_cfg": False,
    "canvas": {"width": 864, "height": 480, "max_pixels": 1344 * 768, "multiple_of": 32},
    "fps": 24.0,
    "frame_length_policy": "h3_generation_frames",
    "sage_attention": "auto",
}

# FLUX stills branch (when stills-only / start-frame path still needs KSampler)
FLUX_STILL: dict[str, Any] = {
    "profile_id": "flux_still",
    "family": "flux",
    "sampler_name": "euler",
    "scheduler": "simple",
    "steps": 28,
    "denoise": 1.0,
    "cfg_scale": 3.5,
    "uses_cfg": True,
    "canvas": {"width": 864, "height": 480, "max_pixels": 1344 * 768, "multiple_of": 32},
}

# Legacy Wan 2.1 — only when explicitly selected; not default for H3 packs
WAN_21: dict[str, Any] = {
    "profile_id": "wan_21",
    "family": "wan",
    "sampler_name": "uni_pc",
    "scheduler": "simple",
    "steps": 30,
    "denoise": 1.0,
    "cfg_scale": 5.5,
    "uses_cfg": True,
    "cfg_range": (1.0, 8.0),
    "steps_range": (16, 40),
    "canvas": {"width": 832, "height": 480, "max_pixels": 832 * 480, "multiple_of": 16},
}

BACKEND_PROFILES: dict[str, dict[str, Any]] = {
    "h3_distilled": H3_DISTILLED,
    "flux_still": FLUX_STILL,
    "wan_21": WAN_21,
}

# quality_tier may nudge H3 steps slightly without inventing CFG
_H3_TIER_STEPS = {
    "draft": 12,
    "standard": 20,
    "high": 24,
    "hero": 28,
}


def get_backend_profile(
    profile_id: str = "h3_distilled",
    *,
    quality_tier: str = "standard",
    motion_complexity: str = "moderate",
) -> dict[str, Any]:
    """Return a concrete sampling dict. Planner must not override steps/cfg directly."""
    key = (profile_id or "h3_distilled").strip().lower()
    if key not in BACKEND_PROFILES:
        raise KeyError(f"unknown backend profile: {profile_id}")
    tier = (quality_tier or "standard").strip().lower()
    if tier not in QUALITY_TIERS:
        raise ValueError(f"quality_tier must be one of {sorted(QUALITY_TIERS)}")
    motion = (motion_complexity or "moderate").strip().lower()
    if motion not in MOTION_COMPLEXITIES:
        raise ValueError(f"motion_complexity must be one of {sorted(MOTION_COMPLEXITIES)}")

    out = deepcopy(BACKEND_PROFILES[key])
    out["quality_tier"] = tier
    out["motion_complexity"] = motion
    if key == "h3_distilled":
        out["steps"] = _H3_TIER_STEPS[tier]
        out["cfg_scale"] = None
        out["uses_cfg"] = False
    elif key == "flux_still":
        # mild tier nudge for stills only
        out["steps"] = {"draft": 16, "standard": 28, "high": 32, "hero": 36}[tier]
    elif key == "wan_21":
        out["steps"] = {"draft": 16, "standard": 30, "high": 36, "hero": 40}[tier]
        out["cfg_scale"] = {"draft": 4.0, "standard": 5.5, "high": 6.5, "hero": 7.0}[tier]
    # motion complexity is advisory metadata for planner/camera text, not sampler math
    out["sampling"] = {
        "steps": out["steps"],
        "scheduler": out["scheduler"],
        "sampler_name": out["sampler_name"],
        "denoise": out["denoise"],
        "cfg_scale": out["cfg_scale"],
    }
    return out


def planner_request_to_hparams(
    *,
    backend_profile: str = "h3_distilled",
    quality_tier: str = "standard",
    motion_complexity: str = "moderate",
) -> dict[str, Any]:
    """Map planner creative request → deterministic hparams for graph binding."""
    prof = get_backend_profile(
        backend_profile,
        quality_tier=quality_tier,
        motion_complexity=motion_complexity,
    )
    hp: dict[str, Any] = {
        "step_count": float(prof["steps"]),
        "denoise": float(prof["denoise"]),
        "scheduler": prof["scheduler"],
        "sampler_name": prof["sampler_name"],
        "backend_profile": prof["profile_id"],
        "quality_tier": prof["quality_tier"],
        "motion_complexity": prof["motion_complexity"],
        "uses_cfg": bool(prof["uses_cfg"]),
    }
    if prof["uses_cfg"] and prof["cfg_scale"] is not None:
        hp["cfg_scale"] = float(prof["cfg_scale"])
    else:
        # Distilled H3: do not invent a CFG for the video sampler
        hp["cfg_scale"] = None
    return hp


def reject_planner_invented_sampling(pred: Any) -> list[str]:
    """Return warnings if a planner object invents Wan/FLUX sampling for H3."""
    warnings: list[str] = []
    backend = str(
        getattr(pred, "backend_profile", None)
        or (pred.get("backend_profile") if isinstance(pred, dict) else None)
        or "h3_distilled"
    ).lower()
    if backend != "h3_distilled":
        return warnings
    for attr in ("cfg", "cfg_scale", "steps", "step_count"):
        if isinstance(pred, dict):
            val = pred.get(attr)
        else:
            val = getattr(pred, attr, None)
        if val is not None and str(val).strip() != "":
            warnings.append(
                f"planner invented {attr}={val!r} for distilled H3; "
                "ignored — use quality_tier / motion_complexity only"
            )
    return warnings


# --- RTX 5080 benchmark starting profiles (audit §12) ----------------------

_BENCHMARK_DIR = Path(__file__).resolve().parent / "benchmark_profiles"


def benchmark_profiles_dir() -> Path:
    return _BENCHMARK_DIR


def list_benchmark_profiles() -> dict[str, dict[str, Any]]:
    """Load all JSON starting profiles from handoff/benchmark_profiles/."""
    out: dict[str, dict[str, Any]] = {}
    root = _BENCHMARK_DIR
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            import json
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        pid = str(data.get("profile_id") or path.stem)
        data = deepcopy(data)
        data["profile_id"] = pid
        data["_source_path"] = str(path)
        out[pid] = data
    return out


def get_benchmark_profile(profile_id: str) -> dict[str, Any]:
    """Return one RTX 5080 starting profile (not a measured guarantee)."""
    key = (profile_id or "").strip()
    all_p = list_benchmark_profiles()
    if key not in all_p:
        raise KeyError(
            f"unknown benchmark profile: {profile_id!r}; "
            f"known={sorted(all_p)}"
        )
    return deepcopy(all_p[key])


def wall_clock_per_accepted_second(
    total_wall_clock_seconds: float,
    accepted_timeline_seconds: float,
) -> float | None:
    """wall-clock per accepted second of video (audit §12 metric).

    Returns None when accepted_timeline_seconds <= 0.
    """
    if accepted_timeline_seconds is None or float(accepted_timeline_seconds) <= 0:
        return None
    return float(total_wall_clock_seconds) / float(accepted_timeline_seconds)


def benchmark_to_backend_hparams(profile_id: str) -> dict[str, Any]:
    """Map a benchmark starting profile onto planner/backend hparams."""
    bench = get_benchmark_profile(profile_id)
    backend = str(bench.get("backend_profile") or "h3_distilled")
    hp = planner_request_to_hparams(
        backend_profile=backend,
        quality_tier="standard",
        motion_complexity="moderate",
    )
    # Overlay explicit sampling from the benchmark JSON when present
    if bench.get("steps") is not None:
        hp["step_count"] = float(bench["steps"])
    if bench.get("denoise") is not None:
        hp["denoise"] = float(bench["denoise"])
    if bench.get("sampler_name"):
        hp["sampler_name"] = bench["sampler_name"]
    if bench.get("scheduler"):
        hp["scheduler"] = bench["scheduler"]
    hp["canvas"] = {
        "width": bench.get("width"),
        "height": bench.get("height"),
    }
    hp["frames"] = bench.get("frames")
    hp["frames_range"] = bench.get("frames_range")
    hp["benchmark_profile_id"] = bench["profile_id"]
    hp["starting_point_only"] = bool(bench.get("starting_point_only", True))
    if bench.get("compatibility_warning") or bench.get("warning"):
        hp["compatibility_warning"] = (
            bench.get("compatibility_warning") or bench.get("warning")
        )
    return hp

