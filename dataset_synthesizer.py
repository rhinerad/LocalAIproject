#!/usr/bin/env python3
"""GVD dataset synthesizer scaffolding (Template-Driven Prompt Decomposition).

DO NOT run while a ComfyUI / GPU batch owns the RTX 5080.
Eventually queries local Ollama qwen2.5:1.5b on 127.0.0.1:11434 to emit
~200 diverse training rows for MIPROv2.

P1-E: validation enforces advertised bounds, multi-scene/dialogue coverage
fields where schema exists, and aligns with shot.schema.json where practical.
P1-C: primary planner fields are quality_tier / motion_complexity (not CFG/steps).
"""
from __future__ import annotations

import json
import random
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT_PATH = ROOT / "local_agent" / "runtime" / "dspy_datasets" / "gvd_decomposition_dataset.jsonl"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5:1.5b"
TARGET_ROWS = 200
SHOT_SCHEMA_PATH = ROOT.parent / "ref_outputs" / "shot.schema.json"

DOMAINS = [
    "coastal drone flyover",
    "macro insect on leaf",
    "neon cyberpunk alley",
    "quiet forest path at dawn",
    "kitchen cooking close-up",
    "desert highway at noon",
    "rainy city crosswalk",
    "mountain ridge hike",
    "underwater coral reef",
    "snowy village street",
    "industrial warehouse interior",
    "rooftop sunset skyline",
    "studio product tabletop",
    "sports stadium night game",
    "library reading aisle",
]

CAMERAS = [
    "static tripod wide shot",
    "slow push-in dolly",
    "handheld documentary shake",
    "aerial orbit",
    "tracking side parallel",
    "crane rise",
    "FPV forward rush",
    "locked-off medium shot",
    "gentle pan left to right",
    "over-the-shoulder follow",
]

LIGHTING = [
    "soft overcast daylight",
    "hard noon sun with crisp shadows",
    "golden hour warm rim light",
    "cool blue moonlight",
    "practical neon practicals only",
    "diffused window light",
    "volumetric god rays through haze",
    "high-key studio softboxes",
    "low-key chiaroscuro",
    "flickering candle warmth",
]

SCHEMA_KEYS = (
    "raw_narrative",
    "subject_and_action",
    "environment",
    "camera_and_motion",
    "lighting_and_style",
    "final_comfyui_prompt",
    "quality_tier",
    "motion_complexity",
)

LEGACY_SAMPLER_KEYS = ("cfg", "denoise", "steps")

QUALITY_TIERS = frozenset({"draft", "standard", "high", "hero"})
MOTION_COMPLEXITIES = frozenset({"static", "subtle", "moderate", "complex"})
CONTINUITY_MODES = frozenset({"cut", "continuous", "reference", "bridge"})

CFG_BOUNDS = (1.0, 8.0)
DENOISE_BOUNDS = (0.35, 1.0)
STEPS_BOUNDS = (16, 40)

SYSTEM = """You synthesize one training example for a Generalized Video Director.
Return ONLY a single JSON object with exactly these keys:
raw_narrative, subject_and_action, environment, camera_and_motion,
lighting_and_style, final_comfyui_prompt, quality_tier, motion_complexity.

Optional coverage fields (include when natural):
  scene_ids (array of strings, multi-scene coverage),
  dialogue (array of {speaker_id, text, voice_asset_id}),
  shot_id, scene_id, duration_frames, characters, action, camera,
  continuity ({mode, parent_attempt_id, canonical_asset_ids}).

Rules:
- Decompose first: subject_and_action, environment, camera_and_motion, lighting_and_style.
- final_comfyui_prompt must compile those fields into one dense ComfyUI-ready string.
- NEVER invent Backrooms / liminal / fluorescent / damp carpet aesthetics unless the
  raw_narrative explicitly asks for them.
- quality_tier is one of: draft | standard | high | hero.
- motion_complexity is one of: static | subtle | moderate | complex.
- Do NOT invent cfg / denoise / steps — backend profiles choose sampling.
- Prefer quality_tier=standard, motion_complexity=moderate unless the domain needs otherwise.
- Across a batch, ensure multi-scene diversity and occasional dialogue coverage.
"""


class DatasetValidationError(ValueError):
    """Raised when a synthesized row fails schema / bounds / coverage checks."""


def _ollama_chat(user_prompt: str) -> str:
    payload = {
        "model": MODEL,
        "stream": False,
        "keep_alive": "0",
        "options": {"num_predict": 2048, "temperature": 0.9},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    }
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    return str(body.get("message", {}).get("content") or "").strip()


def _in_bounds(val: float, lo: float, hi: float) -> bool:
    return lo <= float(val) <= hi


def validate_legacy_sampler_fields(obj: dict) -> None:
    """If legacy cfg/denoise/steps appear, enforce advertised bounds."""
    if "cfg" in obj:
        cfg = float(obj["cfg"])
        if not _in_bounds(cfg, *CFG_BOUNDS):
            raise DatasetValidationError(
                f"cfg={cfg} outside advertised bounds {CFG_BOUNDS}"
            )
        obj["cfg"] = cfg
    if "denoise" in obj:
        denoise = float(obj["denoise"])
        if not _in_bounds(denoise, *DENOISE_BOUNDS):
            raise DatasetValidationError(
                f"denoise={denoise} outside advertised bounds {DENOISE_BOUNDS}"
            )
        obj["denoise"] = denoise
    if "steps" in obj:
        steps = int(obj["steps"])
        if steps < STEPS_BOUNDS[0] or steps > STEPS_BOUNDS[1]:
            raise DatasetValidationError(
                f"steps={steps} outside advertised bounds {STEPS_BOUNDS}"
            )
        obj["steps"] = steps


def validate_dialogue_coverage(dialogue: Any) -> list[dict]:
    """Align dialogue items with shot.schema.json shape."""
    if dialogue is None:
        return []
    if not isinstance(dialogue, list):
        raise DatasetValidationError("dialogue must be an array")
    out: list[dict] = []
    for i, item in enumerate(dialogue):
        if not isinstance(item, dict):
            raise DatasetValidationError(f"dialogue[{i}] must be an object")
        speaker = item.get("speaker_id") or item.get("speaker")
        text = item.get("text")
        if speaker is None or text is None:
            raise DatasetValidationError(
                f"dialogue[{i}] requires speaker_id (or speaker) and text"
            )
        if not str(text).strip():
            raise DatasetValidationError(f"dialogue[{i}].text must be non-empty")
        out.append(
            {
                "speaker_id": str(speaker),
                "text": str(text),
                "voice_asset_id": item.get("voice_asset_id"),
            }
        )
    return out


def validate_continuity(continuity: Any) -> dict | None:
    if continuity is None:
        return None
    if not isinstance(continuity, dict):
        raise DatasetValidationError("continuity must be an object")
    mode = continuity.get("mode")
    if mode not in CONTINUITY_MODES:
        raise DatasetValidationError(
            f"continuity.mode must be one of {sorted(CONTINUITY_MODES)}"
        )
    if "parent_attempt_id" not in continuity:
        raise DatasetValidationError("continuity.parent_attempt_id required")
    assets = continuity.get("canonical_asset_ids")
    if assets is None:
        raise DatasetValidationError("continuity.canonical_asset_ids required")
    if not isinstance(assets, list) or not all(isinstance(x, str) for x in assets):
        raise DatasetValidationError("continuity.canonical_asset_ids must be string[]")
    return {
        "mode": mode,
        "parent_attempt_id": continuity.get("parent_attempt_id"),
        "canonical_asset_ids": list(assets),
    }


def validate_shot_aligned_fields(obj: dict) -> dict:
    """Validate optional shot.schema.json-aligned fields when present."""
    out: dict[str, Any] = {}
    if "shot_id" in obj:
        sid = str(obj["shot_id"] or "")
        if len(sid) < 1:
            raise DatasetValidationError("shot_id minLength 1")
        out["shot_id"] = sid
    if "scene_id" in obj:
        sc = str(obj["scene_id"] or "")
        if len(sc) < 1:
            raise DatasetValidationError("scene_id minLength 1")
        out["scene_id"] = sc
    if "scene_ids" in obj:
        sids = obj["scene_ids"]
        if (
            not isinstance(sids, list)
            or not sids
            or not all(isinstance(x, str) and x for x in sids)
        ):
            raise DatasetValidationError("scene_ids must be non-empty string[]")
        out["scene_ids"] = list(sids)
    if "duration_frames" in obj:
        df = int(obj["duration_frames"])
        if df < 1:
            raise DatasetValidationError("duration_frames minimum 1")
        out["duration_frames"] = df
    if "characters" in obj:
        chars = obj["characters"]
        if not isinstance(chars, list) or not all(isinstance(x, str) for x in chars):
            raise DatasetValidationError("characters must be string[]")
        if len(chars) != len(set(chars)):
            raise DatasetValidationError("characters must be unique")
        out["characters"] = list(chars)
    if "action" in obj:
        out["action"] = str(obj["action"])
    if "camera" in obj:
        out["camera"] = str(obj["camera"])
    if "style" in obj:
        out["style"] = str(obj["style"])
    if "source_span_ids" in obj:
        spans = obj["source_span_ids"]
        if not isinstance(spans, list) or len(spans) < 1:
            raise DatasetValidationError("source_span_ids minItems 1")
        out["source_span_ids"] = list(spans)
    if "dialogue" in obj:
        out["dialogue"] = validate_dialogue_coverage(obj["dialogue"])
    if "continuity" in obj:
        cont = validate_continuity(obj["continuity"])
        if cont is not None:
            out["continuity"] = cont
    return out


def validate_row(obj: dict, *, require_coverage: bool = False) -> dict:
    """Full row validation beyond key presence (P1-E)."""
    if not isinstance(obj, dict):
        raise DatasetValidationError("row must be an object")
    missing = [k for k in SCHEMA_KEYS if k not in obj]
    if missing:
        raise DatasetValidationError(f"missing keys: {missing}")

    for k in SCHEMA_KEYS:
        if k in ("quality_tier", "motion_complexity"):
            continue
        if not isinstance(obj[k], str) or not str(obj[k]).strip():
            raise DatasetValidationError(f"{k} must be a non-empty string")

    tier = str(obj["quality_tier"]).strip().lower()
    motion = str(obj["motion_complexity"]).strip().lower()
    if tier not in QUALITY_TIERS:
        raise DatasetValidationError(
            f"quality_tier={tier!r} not in {sorted(QUALITY_TIERS)}"
        )
    if motion not in MOTION_COMPLEXITIES:
        raise DatasetValidationError(
            f"motion_complexity={motion!r} not in {sorted(MOTION_COMPLEXITIES)}"
        )

    validate_legacy_sampler_fields(obj)
    aligned = validate_shot_aligned_fields(obj)

    if require_coverage:
        has_multi_scene = bool(aligned.get("scene_ids")) and len(aligned["scene_ids"]) >= 2
        has_dialogue = bool(aligned.get("dialogue"))
        if not (has_multi_scene or has_dialogue):
            raise DatasetValidationError(
                "coverage required: need scene_ids (>=2) or non-empty dialogue"
            )

    row = {k: obj[k] for k in SCHEMA_KEYS}
    row["quality_tier"] = tier
    row["motion_complexity"] = motion
    for lk in LEGACY_SAMPLER_KEYS:
        if lk in obj:
            row[lk] = obj[lk]
    row.update(aligned)
    return row


def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise DatasetValidationError("no JSON object in model response")
    obj = json.loads(text[start : end + 1])
    return validate_row(obj)


def _seed_prompt(i: int) -> str:
    domain = random.choice(DOMAINS)
    camera = random.choice(CAMERAS)
    lighting = random.choice(LIGHTING)
    coverage_hint = ""
    if i % 5 == 0:
        coverage_hint = (
            "\nAlso include scene_ids with at least two scenes for multi-scene coverage."
        )
    if i % 7 == 0:
        coverage_hint += (
            "\nAlso include a dialogue array with at least one "
            "{speaker_id, text, voice_asset_id} line."
        )
    return (
        f"Example {i + 1}/{TARGET_ROWS}.\n"
        f"Domain hint: {domain}\n"
        f"Camera hint: {camera}\n"
        f"Lighting hint: {lighting}\n"
        "Invent a short raw_narrative that fits those hints, then fill every schema field."
        f"{coverage_hint}"
    )


def load_shot_schema() -> dict | None:
    if SHOT_SCHEMA_PATH.is_file():
        return json.loads(SHOT_SCHEMA_PATH.read_text(encoding="utf-8"))
    return None


def synthesize(n: int = TARGET_ROWS) -> Path:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with OUT_PATH.open("w", encoding="utf-8") as fh:
        for i in range(n):
            raw = _ollama_chat(_seed_prompt(i))
            row = _extract_json(raw)
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
            print(f"wrote {written}/{n}", flush=True)
    print(f"saved {written} rows -> {OUT_PATH}", flush=True)
    return OUT_PATH


if __name__ == "__main__":
    # Manual run only when GPU/LLM lane is free.
    synthesize(TARGET_ROWS)
