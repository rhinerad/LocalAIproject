#!/usr/bin/env python3
"""Shared MiniMax H3 graph builders for production (dotted Autogrow keys)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

REF2VA_CLASS = "MiniMaxH3ReferenceToVideo"
I2V_CLASS = "MiniMaxH3ImageToVideo"
MAX_REF_IMAGES = 9
MAX_REF_AUDIOS = 3


class GraphBuildError(ValueError):
    pass


@dataclass
class ImageRef:
    comfy_input_name: str
    character_id: str | None = None
    role: str = "identity"  # identity | boundary | composition


@dataclass
class AudioRef:
    comfy_input_name: str
    character_id: str
    exact_transcript: str
    purpose: str = "voice_identity"  # never "speech_to_replay"


@dataclass
class RefBindingPlan:
    images: list[ImageRef] = field(default_factory=list)
    audios: list[AudioRef] = field(default_factory=list)

    def validate(self) -> None:
        if len(self.images) > MAX_REF_IMAGES:
            raise GraphBuildError(
                f"{len(self.images)} image refs exceed MiniMax max {MAX_REF_IMAGES}; replan shot"
            )
        if len(self.audios) > MAX_REF_AUDIOS:
            raise GraphBuildError(
                f"{len(self.audios)} audio refs exceed MiniMax max {MAX_REF_AUDIOS}; split/replan shot"
            )
        for a in self.audios:
            if not a.character_id:
                raise GraphBuildError("audio ref missing character_id")
            if a.purpose != "voice_identity":
                raise GraphBuildError("audio refs must be voice_identity, not speech replay")
            if not str(a.exact_transcript or "").strip():
                raise GraphBuildError(f"audio ref for {a.character_id} missing exact_transcript")


def build_prompt_with_ref_tags(
    base_prompt: str,
    plan: RefBindingPlan,
    *,
    map_audio_to_character: bool = True,
) -> str:
    """Ensure <Picture i> / <Audio j> tags and explicit speaker mapping."""
    plan.validate()
    text = (base_prompt or "").strip()
    for i, _img in enumerate(plan.images, start=1):
        tag = f"<Picture {i}>"
        if tag not in text and f"<Picture{i}>" not in text:
            text = f"{tag} " + text
    for j, audio in enumerate(plan.audios, start=1):
        tag = f"<Audio {j}>"
        if tag not in text and f"<Audio{j}>" not in text:
            if map_audio_to_character:
                text += (
                    f" Character {audio.character_id} speaks with the same voice identity as {tag}"
                    f" (voice reference only; do not replay the reference speech)."
                )
            else:
                text += f" Speak with the same voice as {tag}."
    return text.strip()


def emit_autogrow_image_inputs(plan: RefBindingPlan, load_node_ids: Sequence[str]) -> dict[str, list]:
    """Map LoadImage node ids -> dotted keys ref_images.ref_image_N."""
    plan.validate()
    if len(load_node_ids) != len(plan.images):
        raise GraphBuildError("load_node_ids length must match plan.images")
    out: dict[str, list] = {}
    for i, nid in enumerate(load_node_ids):
        out[f"ref_images.ref_image_{i}"] = [str(nid), 0]
    return out


def emit_autogrow_audio_inputs(plan: RefBindingPlan, load_node_ids: Sequence[str]) -> dict[str, list]:
    """Map LoadAudio node ids -> dotted keys ref_audios.ref_audio_N."""
    plan.validate()
    if len(load_node_ids) != len(plan.audios):
        raise GraphBuildError("audio load_node_ids length must match plan.audios")
    out: dict[str, list] = {}
    for i, nid in enumerate(load_node_ids):
        out[f"ref_audios.ref_audio_{i}"] = [str(nid), 0]
    return out


def character_to_audio_tag_map(plan: RefBindingPlan) -> dict[str, str]:
    plan.validate()
    return {a.character_id: f"<Audio {i}>" for i, a in enumerate(plan.audios, start=1)}


def apply_ref2va_autogrow(
    graph: dict[str, Any],
    *,
    prompt: str,
    plan: RefBindingPlan,
    width: int,
    height: int,
    length: int,
    clip_node: list | None = None,
    vae_node: list | None = None,
    audio_vae_node: list | None = None,
    ref_image_size: str = "match",
    ref2va_node_id: str = "20",
    image_load_start_id: int = 9000,
    audio_load_start_id: int = 9100,
) -> dict[str, Any]:
    """Mutate/return graph with MiniMaxH3ReferenceToVideo + LoadImage/LoadAudio Autogrow wiring."""
    plan.validate()
    g = dict(graph)
    img_ids: list[str] = []
    for i, img in enumerate(plan.images):
        nid = str(image_load_start_id + i)
        g[nid] = {"class_type": "LoadImage", "inputs": {"image": img.comfy_input_name}}
        img_ids.append(nid)
    aud_ids: list[str] = []
    for i, aud in enumerate(plan.audios):
        nid = str(audio_load_start_id + i)
        g[nid] = {"class_type": "LoadAudio", "inputs": {"audio": aud.comfy_input_name}}
        aud_ids.append(nid)

    inputs: dict[str, Any] = {
        "prompt": build_prompt_with_ref_tags(prompt, plan),
        "width": int(width),
        "height": int(height),
        "length": int(length),
        "ref_image_size": ref_image_size,
    }
    if clip_node is not None:
        inputs["clip"] = clip_node
    elif "31" in g:
        inputs["clip"] = ["31", 0]
    if vae_node is not None:
        inputs["vae"] = vae_node
    elif "32" in g:
        inputs["vae"] = ["32", 0]
    if audio_vae_node is not None:
        inputs["audio_vae"] = audio_vae_node
    inputs.update(emit_autogrow_image_inputs(plan, img_ids))
    inputs.update(emit_autogrow_audio_inputs(plan, aud_ids))

    # Replace I2V node if present
    node = g.get(ref2va_node_id) or {}
    if isinstance(node, dict) and node.get("class_type") in {I2V_CLASS, REF2VA_CLASS, None}:
        prev = dict(node.get("inputs") or {})
        for k in ("first_frame", "ref_images", "ref_image_0"):
            prev.pop(k, None)
        prev.update(inputs)
        g[ref2va_node_id] = {"class_type": REF2VA_CLASS, "inputs": prev}
    else:
        g[ref2va_node_id] = {"class_type": REF2VA_CLASS, "inputs": inputs}
    return g


def assert_no_bare_ref_images_key(graph: dict[str, Any]) -> None:
    for nid, node in graph.items():
        if not isinstance(node, dict):
            continue
        if node.get("class_type") != REF2VA_CLASS:
            continue
        inputs = node.get("inputs") or {}
        if "ref_images" in inputs:
            raise GraphBuildError(
                f"node {nid}: bare ref_images key is invalid; use ref_images.ref_image_N"
            )
        bare = [k for k in inputs if __import__("re").fullmatch(r"ref_image_\d+", str(k))]
        if bare:
            raise GraphBuildError(
                f"node {nid}: bare {bare} invalid; use ref_images.ref_image_N"
            )
