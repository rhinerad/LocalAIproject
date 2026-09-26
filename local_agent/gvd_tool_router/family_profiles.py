"""M3: map the installed Comfy tree onto GVD families. Unknown VRAM stays blocked."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .inventory import DEFAULT_COMFY_ROOT
from .paths import GvdLayout

# Folder-name needles. Presence is not a local resource profile.
FAMILY_NODES: dict[str, tuple[str, ...]] = {
    "narrative_identity": ("storydiffusion", "comfyui_storydiffusion"),
    "ipadapter": ("ipadapter",),
    "still_generation": ("hf-flux", "flux"),
    "controlnet_aux": ("controlnet_aux",),
    "tiled_diffusion": ("tileddiffusion",),
    "montage_morph": ("animatediff", "fizznodes"),
    "video_helper": ("videohelpersuite",),
    "tts_f5": ("f5-tts", "f5tts"),
    "lipsync_musetalk": ("musetalk",),
    "sam2": ("sam2", "segment-anything-2"),
    "repair_propainter": ("propainter",),
    "wan": ("wanvideowrapper", "wan22fmlf"),
    "continuous_longcat": ("longcat",),
    "fast_ltx": ("ltxvideo", "ltx-video"),
    "fast_h3": ("minimax-h3", "minimax_h3", "feihou-easy-h3"),
    "qa_wd14": ("wd14-tagger", "wd14tagger"),
    "qa_yrikka_its": ("inferencetimescaling", "yrikka"),
    "qa_image_eval": ("image-evaluation", "imageevaluation"),
}

FAMILY_TO_TOOL = {
    "narrative_identity": "execute_narrative_scene",
    "ipadapter": "execute_narrative_scene",
    "still_generation": "generate_still",
    "montage_morph": "execute_montage_morph",
    "fast_ltx": "execute_fast_action",
    "fast_h3": "execute_fast_action",
    "continuous_longcat": "execute_continuous_take",
    "wan": "execute_continuous_take",
    "tts_f5": "synthesize_dialogue",
    "lipsync_musetalk": "apply_lipsync",
    "repair_propainter": "repair_video",
    "qa_wd14": "gvd_qa_evaluate",
}


def list_custom_node_dirs(comfy_root: Path | None = None) -> list[str]:
    root = Path(comfy_root or DEFAULT_COMFY_ROOT) / "custom_nodes"
    if not root.is_dir():
        return []
    names = []
    for child in root.iterdir():
        if child.name.startswith("."):
            continue
        names.append(child.name)
    return sorted(names)


def _match(folder: str, needles: tuple[str, ...]) -> bool:
    lowered = folder.lower().replace("-", "").replace("_", "")
    if folder.lower().endswith(".disabled"):
        return False
    for needle in needles:
        compact = needle.lower().replace("-", "").replace("_", "")
        if compact and compact in lowered:
            return True
    return False


def scan_families(comfy_root: Path | None = None) -> dict[str, Any]:
    folders = list_custom_node_dirs(comfy_root)
    families: dict[str, Any] = {}
    for family, needles in FAMILY_NODES.items():
        hits = [f for f in folders if _match(f, needles)]
        if hits:
            families[family] = {
                "installed": True,
                "folders": hits,
                "activation": "blocked_pending_local_profile",
                "reason": "nodes present; no local peak_gpu_mib profile has been measured",
                "tool": FAMILY_TO_TOOL.get(family),
            }
        else:
            families[family] = {
                "installed": False,
                "folders": [],
                "activation": "blocked_missing_nodes",
                "reason": "required custom-node pack is not in custom_nodes",
                "tool": FAMILY_TO_TOOL.get(family),
            }
    return {
        "custom_node_count": len(folders),
        "families": families,
        "note": "Installed folders do not activate implementations. Local VRAM evidence is required.",
    }


def write_family_report(layout: GvdLayout, comfy_root: Path | None = None) -> Path:
    layout.ensure()
    report = scan_families(comfy_root)
    path = layout.inventory_dir / "family_status.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
