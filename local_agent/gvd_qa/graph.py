"""API-graph helpers: route IMAGE outputs through WD14 before SaveImage."""
from __future__ import annotations

from typing import Any

from .constants import WD14_CLASS


def find_image_output_nodes(graph: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (node_id, output_slot_name) pairs that emit IMAGE."""
    hits: list[tuple[str, str]] = []
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type") or "")
        if cls in {"SaveImage", "PreviewImage", "VHS_VideoCombine"}:
            continue
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
        # Heuristic: KSampler/VAEDecode-style nodes are the usual IMAGE producers.
        if cls in {"VAEDecode", "VAEDecodeTiled", "ImageFromBatch", "ImageScale", "ImageResize"}:
            hits.append((str(node_id), "IMAGE"))
            continue
        if "image" in {k.lower() for k in inputs} and cls.startswith("Load"):
            continue
    if not hits:
        for node_id, node in graph.items():
            if isinstance(node, dict) and str(node.get("class_type") or "") == "VAEDecode":
                hits.append((str(node_id), "IMAGE"))
    return hits


def _next_node_id(graph: dict[str, Any]) -> str:
    numeric = []
    for key in graph:
        try:
            numeric.append(int(key))
        except (TypeError, ValueError):
            continue
    return str((max(numeric) + 1) if numeric else 1)


def attach_wd14_tagger(
    graph: dict[str, Any],
    *,
    image_node_id: str,
    image_slot: int | str = 0,
    node_id: str | None = None,
    model: str = "wd-v1-4-moat-tagger-v2",
    threshold: float = 0.35,
    character_threshold: float = 0.85,
) -> dict[str, Any]:
    """Return a copy of `graph` with WD14 tagging the given IMAGE output.

    SaveImage / VHS combine nodes are left in place. WD14 is an extra
    OUTPUT_NODE so `/history` carries tags without changing the saved bytes.
    """
    if not isinstance(graph, dict) or not graph:
        raise ValueError("API graph must be a non-empty node map")
    if str(image_node_id) not in graph and image_node_id not in graph:
        raise ValueError(f"image node {image_node_id!r} is not in the graph")
    out = {key: (dict(value) if isinstance(value, dict) else value) for key, value in graph.items()}
    for key, value in list(out.items()):
        if isinstance(value, dict) and "inputs" in value and isinstance(value["inputs"], dict):
            out[key] = {**value, "inputs": dict(value["inputs"])}
    tag_id = node_id or _next_node_id(out)
    if tag_id in out:
        raise ValueError(f"node id {tag_id!r} already exists")
    slot = int(image_slot) if str(image_slot).isdigit() else 0
    out[tag_id] = {
        "class_type": WD14_CLASS,
        "inputs": {
            "image": [str(image_node_id), slot],
            "model": model,
            "threshold": float(threshold),
            "character_threshold": float(character_threshold),
            "replace_underscore": True,
            "trailing_comma": False,
            "exclude_tags": "",
        },
    }
    return out
