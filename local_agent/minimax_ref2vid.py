#!/usr/bin/env python3
"""MiniMax H3 Reference-To-Video staging helpers (C002+).

Transforms the live FLUX + MiniMaxH3ImageToVideo graph into
MiniMaxH3ReferenceToVideo conditioned on:
  - C001 still  (ComfyUI/input/C001_ref_still.png) as <Picture 1>
  - C001 master voice (ComfyUI/input/C001_master_voice.wav) as <Audio 1>

Does NOT change the C001 MiniMaxH3ImageToVideo path. Opt-in only via
clip override / caller flag. Prefer MiniMax-native audio decode mux
(same as C001) instead of Fish/F5 TTS.

STAGED: import and call from build_minimax_graph only after PATCH applied.
"""
from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Any

C001_REF_STILL = os.environ.get("GVD_C001_REF_STILL", "C001_ref_still.png")
C001_MASTER_VOICE_WAV = os.environ.get("GVD_C001_MASTER_VOICE_WAV", "C001_master_voice.wav")
MINIMAX_AUDIO_VAE_NAME = os.environ.get(
    "GVD_MINIMAX_AUDIO_VAE", "minimax_h3_audio_vae_fp32.safetensors"
)
REF2VID_CLASS = "MiniMaxH3ReferenceToVideo"
LOAD_IMAGE_CLASS = "LoadImage"
LOAD_AUDIO_CLASS = "LoadAudio"
import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parents[1]
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

# Production Autogrow helper (shared). Prefer this over ad-hoc C001_master_voice defaults.
try:
    from gvd_graph_builder import (  # type: ignore
        AudioRef,
        ImageRef,
        RefBindingPlan,
        apply_ref2va_autogrow,
        assert_no_bare_ref_images_key,
    )
    _HAS_GVD_GRAPH = True
except Exception:  # pragma: no cover
    _HAS_GVD_GRAPH = False


def apply_minimax_ref2vid_from_plan(
    graph: dict,
    *,
    video_prompt: str,
    plan,
    width: int | None = None,
    height: int | None = None,
    length: int | None = None,
):
    """Production entry: bind per-character image/audio refs via dotted Autogrow keys."""
    if not _HAS_GVD_GRAPH:
        raise RuntimeError("gvd_graph_builder unavailable; cannot emit production Autogrow keys")
    # Allow import from local_agent/ by adding parent to path lazily
    w = int(width or 864)
    h = int(height or 480)
    n = int(length or 124)
    g = apply_ref2va_autogrow(
        graph,
        prompt=video_prompt,
        plan=plan,
        width=w,
        height=h,
        length=n,
    )
    assert_no_bare_ref_images_key(g)
    return g



def _canonical_clip_id(clip_id: str) -> str:
    raw = str(clip_id or "").strip().upper()
    m = re.search(r"C0*([0-9]{1,3})\b", raw)
    if m:
        return f"C{int(m.group(1)):03d}"
    if raw in {"1", "001"}:
        return "C001"
    return raw


def _load_clip_override(clip_id: str) -> dict:
    """Best-effort read of clip_overrides/C00X.json (no throw)."""
    cid = _canonical_clip_id(clip_id)
    if not cid.startswith("C"):
        return {}
    # local_agent/../clip_overrides
    here = Path(__file__).resolve().parent
    for base in (here.parent / "clip_overrides", here / "clip_overrides"):
        path = base / f"{cid}.json"
        if path.is_file():
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
                return obj if isinstance(obj, dict) else {}
            except Exception:
                return {}
    return {}


def wants_minimax_ref2vid(clip_id: str, override: dict | None = None) -> bool:
    """Opt-in gate. Never true for C001 (keeps native I2V + MiniMax audio)."""
    cid = _canonical_clip_id(clip_id)
    if cid == "C001":
        return False
    ov = override if isinstance(override, dict) else {}
    if not ov:
        ov = _load_clip_override(clip_id)
    if ov.get("minimax_ref2vid") or ov.get("use_minimax_ref2vid"):
        return True
    if str(ov.get("minimax_mode") or "").lower() in {"ref2vid", "reference", "reference_to_video"}:
        return True
    return os.environ.get("GVD_MINIMAX_REF2VID", "0") == "1"


def _ensure_picture_audio_tags(prompt: str) -> str:
    text = (prompt or "").strip()
    # MiniMax H3 ReferenceToVideo expects <Picture i> / <Audio j> tags in the prompt.
    if "<Picture 1>" not in text and "<Picture1>" not in text:
        text = "<Picture 1> " + text
    if "<Audio 1>" not in text and "<Audio1>" not in text:
        text = text + " Speak with the same voice as <Audio 1>."
    return text


def apply_minimax_ref2vid(
    graph: dict,
    *,
    video_prompt: str,
    ref_still_name: str = C001_REF_STILL,
    ref_audio_name: str = C001_MASTER_VOICE_WAV,  # legacy default; prefer apply_minimax_ref2vid_from_plan
    width: int | None = None,
    height: int | None = None,
    length: int | None = None,
) -> dict:
    """Swap MiniMaxH3ImageToVideo -> MiniMaxH3ReferenceToVideo + LoadImage/LoadAudio.

    Node IDs (non-colliding with FLUX 1-14 and MiniMax 20-41 / voice 42-44 / fish 90-92):
      50 LoadImage (C001 still)
      51 LoadAudio (C001 master voice)
      52 VAELoader audio VAE
      20 replaced in-place with ReferenceToVideo
    """
    if not isinstance(graph, dict):
        raise TypeError("graph must be dict")
    g = copy.deepcopy(graph)
    g.pop("_meta", None)

    node20 = g.get("20")
    if not isinstance(node20, dict):
        raise RuntimeError("ref2vid transform expected node 20 (MiniMax I2V) in graph")

    prev = dict(node20.get("inputs") or {})
    clip = prev.get("clip") or ["31", 0]
    vae = prev.get("vae") or ["32", 0]
    w = int(width if width is not None else prev.get("width") or 1280)
    h = int(height if height is not None else prev.get("height") or 704)
    n = int(length if length is not None else prev.get("length") or 192)
    prompt = _ensure_picture_audio_tags(str(video_prompt or prev.get("prompt") or ""))

    g["50"] = {
        "class_type": LOAD_IMAGE_CLASS,
        "inputs": {"image": ref_still_name},
    }
    g["51"] = {
        "class_type": LOAD_AUDIO_CLASS,
        "inputs": {"audio": ref_audio_name},
    }
    g["52"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": MINIMAX_AUDIO_VAE_NAME},
    }

    # API-style autogrow keys mirror Fish Audio / Comfy UI templates:
    # ref_images.ref_image_0, ref_audios.ref_audio_0
    g["20"] = {
        "class_type": REF2VID_CLASS,
        "inputs": {
            "clip": clip,
            "prompt": prompt,
            "width": w,
            "height": h,
            "length": n,
            "ref_image_size": "match",
            "vae": vae,
            "audio_vae": ["52", 0],
            "ref_images.ref_image_0": ["50", 0],
            "ref_audios.ref_audio_0": ["51", 0],
        },
    }

    # Keep SamplerCustomAdvanced latent from node 20 output 1 (unchanged wiring).
    # Caller should mux MiniMax-native audio (C001-style VAEDecodeAudio) rather than Fish/F5.
    return g


def attach_minimax_native_audio_mux(graph: dict) -> dict:
    """Reuse C001 MiniMax native audio decode into CreateVideo.audio.

    Adds/overwrites nodes 42/43/44 and wires CreateVideo/VHS audio.
    Safe to call after apply_minimax_ref2vid for C002+.
    """
    if not isinstance(graph, dict):
        raise TypeError("graph must be dict")
    g = graph

    create_id = None
    for nid, node in g.items():
        if isinstance(node, dict) and node.get("class_type") == "CreateVideo":
            create_id = str(nid)
            break
    if create_id is None:
        return g

    sampler_id = None
    for nid, node in g.items():
        if isinstance(node, dict) and node.get("class_type") == "SamplerCustomAdvanced":
            sampler_id = str(nid)
            break
    sampler_id = sampler_id or "37"

    g["42"] = {
        "class_type": "VAELoader",
        "inputs": {"vae_name": MINIMAX_AUDIO_VAE_NAME},
    }
    g["43"] = {
        "class_type": "VAEDecodeAudio",
        "inputs": {"samples": [sampler_id, 0], "vae": ["42", 0]},
    }
    g["44"] = {
        "class_type": "SanitizeGeneratedAudio",
        "inputs": {"audio": ["43", 0]},
    }
    inputs = dict(g[create_id].get("inputs") or {})
    inputs["audio"] = ["44", 0]
    g[create_id] = {**g[create_id], "inputs": inputs}
    return g
