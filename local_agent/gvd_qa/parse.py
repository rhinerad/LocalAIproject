"""Parse verifier scores out of a Comfy `/history` payload or node outputs."""
from __future__ import annotations

import json
import re
from typing import Any

from .constants import (
    WU_CLIP_CLASSES,
    WU_DINO_CLASSES,
    WD14_CLASS,
    YRIKKA_CLIP_CLASSES,
    YRIKKA_IMAGE_REWARD_CLASSES,
    YRIKKA_QWEN_CLASSES,
)

_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.\d+|\d+)")


def _class_type(node: dict[str, Any]) -> str:
    return str(node.get("class_type") or node.get("classType") or "")


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "pass", "yes", "1"}:
        return True
    if text in {"false", "fail", "no", "0"}:
        return False
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, (list, tuple)) and value:
        return _as_float(value[0])
    if isinstance(value, dict):
        for key in ("score", "value", "clip_score", "image_reward"):
            if key in value:
                parsed = _as_float(value[key])
                if parsed is not None:
                    return parsed
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        match = _FLOAT_RE.search(text)
        return float(match.group(0)) if match else None


def _flatten_outputs(outputs: Any) -> list[Any]:
    if outputs is None:
        return []
    if isinstance(outputs, dict):
        items: list[Any] = []
        for key in ("text", "tags", "result", "images", "gifs"):
            if key in outputs:
                items.extend(_flatten_outputs(outputs[key]))
        if "ui" in outputs:
            items.extend(_flatten_outputs(outputs["ui"]))
        if not items:
            items.extend(outputs.values())
        return items
    if isinstance(outputs, (list, tuple)):
        out: list[Any] = []
        for item in outputs:
            out.extend(_flatten_outputs(item))
        return out
    return [outputs]


def _wd14_tags(value: Any) -> list[str]:
    tags: list[str] = []
    if isinstance(value, list):
        for item in value:
            tags.extend(_wd14_tags(item))
        return tags
    text = str(value or "")
    for part in re.split(r"[,;\n]+", text):
        token = part.strip().lower().replace("_", " ")
        if token:
            tags.append(token)
    return tags


def parse_verifier_outputs(
    history: dict[str, Any] | None,
    *,
    graph: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract CLIP / ImageReward / Qwen-VL / WD14 values from history+graph."""
    history = history or {}
    outputs = history.get("outputs") if isinstance(history.get("outputs"), dict) else history
    prompt = history.get("prompt")
    if isinstance(prompt, dict) and "outputs" in prompt and not outputs:
        outputs = prompt.get("outputs") or {}
    if not isinstance(outputs, dict):
        outputs = {}

    graph = graph or history.get("prompt") or {}
    if isinstance(graph, list) and len(graph) >= 3 and isinstance(graph[2], dict):
        graph = graph[2]
    if not isinstance(graph, dict):
        graph = {}

    result = {
        "qwen_vl": None,
        "clip_score": None,
        "image_reward": None,
        "dino_score": None,
        "wd14_tags": [],
        "sources": [],
        "raw_text": [],
    }

    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        cls = _class_type(node)
        node_out = outputs.get(str(node_id)) or outputs.get(node_id) or {}
        values = _flatten_outputs(node_out)
        if cls == WD14_CLASS or "WD14Tagger" in cls:
            for value in values:
                result["wd14_tags"].extend(_wd14_tags(value))
            if values:
                result["sources"].append("wd14")
        elif cls in YRIKKA_QWEN_CLASSES or "QwenVLM" in cls.replace(" ", ""):
            for value in values:
                parsed = _as_bool(value)
                if parsed is not None:
                    result["qwen_vl"] = parsed
                    result["sources"].append("yrikka_qwen_vl")
                    break
        elif cls in YRIKKA_IMAGE_REWARD_CLASSES or "ImageReward" in cls.replace(" ", ""):
            for value in values:
                parsed = _as_float(value)
                if parsed is not None:
                    result["image_reward"] = parsed
                    result["sources"].append("yrikka_image_reward")
                    break
        elif cls in YRIKKA_CLIP_CLASSES + WU_CLIP_CLASSES or "CLIPScore" in cls.replace(" ", ""):
            for value in values:
                parsed = _as_float(value)
                if parsed is not None:
                    result["clip_score"] = parsed
                    result["sources"].append("clip_score")
                    break
        elif cls in WU_DINO_CLASSES or "DINO" in cls.upper():
            for value in values:
                parsed = _as_float(value)
                if parsed is not None:
                    result["dino_score"] = parsed
                    result["sources"].append("dino")
                    break

    if not result["wd14_tags"]:
        ui = history.get("status") if isinstance(history.get("status"), dict) else {}
        extra = history.get("meta") or {}
        blob = json.dumps({"outputs": outputs, "ui": ui, "meta": extra}, default=str)
        if "WD14" in blob or "wd14" in blob.lower():
            result["wd14_tags"].extend(_wd14_tags(blob))

    seen = []
    for tag in result["wd14_tags"]:
        if tag not in seen:
            seen.append(tag)
    result["wd14_tags"] = seen
    return result
