#!/usr/bin/env python3
"""Read-only local 3D capability inventory; never loads a model or queues work."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_SHARED_ROOT = Path(r"A:\Users\rhine\ComfyUI-Shared")
MODEL_MARKERS = {
    "trellis": ("TRELLIS", "trellis"),
    "hunyuan3d": ("hunyuan3d", "Hunyuan3D"),
    "stable_fast_3d": ("stable-fast-3d", "stable_fast_3d", "sf3d"),
}


def _matches(path: Path, markers: tuple[str, ...]) -> bool:
    return any(marker.lower() in str(path).lower() for marker in markers)


def _model_asset(path: Path) -> bool:
    """Exclude caches/readmes; retain weight files and small runtime manifests."""
    return (".cache" not in path.parts and path.suffix.lower() in
            {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".json"})


def inspect(root: Path | None = None) -> dict:
    """Return installed asset/workflow facts, not a readiness claim."""
    root = Path(root or os.environ.get("EQUAL_SHARES_COMFY_SHARED", DEFAULT_SHARED_ROOT))
    models, workflows = root / "models", root / "workflows"
    result = {"root": str(root), "exists": root.is_dir(), "models": {}, "workflows": []}
    if not root.is_dir():
        result["reason"] = "Shared ComfyUI root is unavailable."
        return result
    model_files = list(models.rglob("*")) if models.is_dir() else []
    for name, markers in MODEL_MARKERS.items():
        result["models"][name] = [{"path": str(path), "bytes": path.stat().st_size}
                                  for path in model_files if path.is_file()
                                  and _model_asset(path) and _matches(path, markers)]
    workflow_files = list(workflows.rglob("*.json")) if workflows.is_dir() else []
    result["workflows"] = [str(path) for path in workflow_files
                           if _matches(path, sum(MODEL_MARKERS.values(), ()))]
    result["routing_ready"] = False
    result["reason"] = ("Model assets alone are insufficient. A reviewed ComfyUI API workflow, "
                        "installed node types, output contract, preflight, and GPU ownership test "
                        "are required before a 3D tool can exist.")
    return result


if __name__ == "__main__":
    print(json.dumps(inspect(), indent=2))
