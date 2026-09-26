#!/usr/bin/env python3
"""Dynamic ComfyUI API-graph construction with safe link rewiring.

ComfyUI prompt JSON identifies nodes by string ids and encodes edges as
``[node_id, output_slot]`` arrays (``{"images": ["14", 0]}``). This module
never invents those ids: every new node gets ``max(existing)+1``, and every
rewire copies the live link that already sits on the consumer.

Not used by ``work/image_render.py``'s default t2i path: that renderer starts
ComfyUI with custom nodes disabled. FaceDetailer lives here so Impact Pack
injection is opt-in for the media pipeline.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

# Impact Pack bbox detector used by work/image_render.py FaceDetailer graphs.
FACE_DETAIL_MODEL = "bbox/face_yolov8m.pt"
FACE_DETAIL_POSITIVE = (
    "natural photorealistic face, symmetrical eyes, aligned pupils, detailed irises, "
    "natural skin texture, anatomically correct facial features"
)
FACE_DETAIL_NEGATIVE = (
    "cross-eyed, crossed eyes, strabismus, lazy eye, wall-eyed, misaligned pupils, "
    "asymmetrical eyes, malformed face, deformed face, duplicate face, blurry face"
)

# Task 3 keyword list. Word boundaries so "manager" / "surface" do not match.
_HUMAN_SUBJECT_RE = re.compile(
    r"\b(?:men|women|people|person|woman|girl|boy|man|face|portrait)\b",
    re.IGNORECASE,
)
_PROHIBITION_SENTENCE_RE = re.compile(
    r"\b(?:do not depict|do not show|never show|no)\b[^.]*\.",
    re.IGNORECASE,
)
_ABSENCE_RE = re.compile(
    r"\babsence of a (?:person|people|human|face)\b",
    re.IGNORECASE,
)

SAVE_NODE_TYPES = frozenset({"SaveImage", "SaveImageWebsocket"})


class ComfyGraphError(ValueError):
    """The graph is missing a required node or a link is malformed."""


def prompt_requests_human_subject(prompt: str) -> bool:
    """True when the finalized prompt positively requests a human subject.

    Prohibitive clauses ("Do not depict the actor's face or torso.") and
    "absence of a person" statements are stripped first so Mode B empty
    plates do not pull in FaceDetailer.
    """
    text = str(prompt or "").lower()
    text = _PROHIBITION_SENTENCE_RE.sub(" ", text)
    text = _ABSENCE_RE.sub(" ", text)
    # Temporal-physics "first-person camcorder" must not count as a person.
    text = re.sub(r"\bfirst-person\b", " ", text)
    return bool(_HUMAN_SUBJECT_RE.search(text))


def _as_link(value: Any) -> list | None:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    node_id, slot = value[0], value[1]
    if not str(node_id) or not isinstance(slot, int):
        return None
    return [str(node_id), int(slot)]


def base_txt2img_workflow(
    *,
    prompt: str = "",
    negative_prompt: str = "",
    checkpoint: str = "RealVisXL_V5.0_fp16.safetensors",
    width: int = 1024,
    height: int = 768,
    steps: int = 30,
    cfg: float = 7.0,
    seed: int = 42,
    sampler: str = "euler",
    scheduler: str = "normal",
    filename_prefix: str = "media_pipeline",
    save_class: str = "SaveImageWebsocket",
) -> dict[str, Any]:
    """Canonical txt2img API graph. All node ids are strings; all links are arrays."""
    if save_class not in SAVE_NODE_TYPES:
        raise ComfyGraphError(f"save_class must be SaveImage or SaveImageWebsocket, got {save_class!r}")
    save_inputs: dict[str, Any] = {"images": ["6", 0]}
    if save_class == "SaveImage":
        save_inputs["filename_prefix"] = filename_prefix
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": checkpoint},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": prompt, "clip": ["1", 1]},
            "_meta": {"title": "Positive Prompt"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": negative_prompt, "clip": ["1", 1]},
            "_meta": {"title": "Negative Prompt"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": int(width), "height": int(height), "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": int(seed),
                "steps": int(steps),
                "cfg": float(cfg),
                "sampler_name": sampler,
                "scheduler": scheduler,
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": save_class,
            "inputs": save_inputs,
        },
    }


class ComfyGraphBuilder:
    """Mutating builder over a ComfyUI API-format prompt dict."""

    def __init__(self, graph: dict[str, Any] | None = None):
        self.graph: dict[str, Any] = copy.deepcopy(graph or base_txt2img_workflow())
        self._validate_nodes()

    @classmethod
    def from_txt2img(cls, **kwargs: Any) -> "ComfyGraphBuilder":
        return cls(base_txt2img_workflow(**kwargs))

    @classmethod
    def from_json_file(cls, path: str | Path) -> "ComfyGraphBuilder":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ComfyGraphError("workflow JSON must be an object of node id -> node")
        # Accept a raw graph or a {"prompt": {...}} envelope.
        graph = payload.get("prompt") if isinstance(payload.get("prompt"), dict) else payload
        return cls(graph)

    def _validate_nodes(self) -> None:
        if not isinstance(self.graph, dict) or not self.graph:
            raise ComfyGraphError("graph is empty")
        for node_id, node in self.graph.items():
            if not isinstance(node, dict) or "class_type" not in node:
                raise ComfyGraphError(f"node {node_id!r} is missing class_type")
            node.setdefault("inputs", {})
            if not isinstance(node["inputs"], dict):
                raise ComfyGraphError(f"node {node_id!r} inputs must be an object")

    def node_ids_of(self, class_type: str) -> list[str]:
        return [
            str(node_id)
            for node_id, node in self.graph.items()
            if node.get("class_type") == class_type
        ]

    def require_one(self, class_type: str) -> str:
        ids = self.node_ids_of(class_type)
        if not ids:
            raise ComfyGraphError(f"graph has no {class_type} node")
        return ids[0]

    def alloc_id(self) -> str:
        used = [int(k) for k in self.graph if str(k).isdigit()]
        n = (max(used) + 1) if used else 1
        while str(n) in self.graph:
            n += 1
        return str(n)

    def add_node(self, class_type: str, inputs: dict[str, Any], *, node_id: str | None = None,
                 meta: dict | None = None) -> str:
        new_id = str(node_id) if node_id else self.alloc_id()
        if new_id in self.graph:
            raise ComfyGraphError(f"node id {new_id!r} already exists")
        payload: dict[str, Any] = {
            "class_type": class_type,
            "inputs": copy.deepcopy(inputs),
        }
        if meta:
            payload["_meta"] = dict(meta)
        self.graph[new_id] = payload
        return new_id

    def consumers_of(self, source_id: str, output_slot: int) -> list[tuple[str, str]]:
        """Return (node_id, input_name) that currently read ``[source_id, output_slot]``."""
        source_id = str(source_id)
        found: list[tuple[str, str]] = []
        for node_id, node in self.graph.items():
            inputs = node.get("inputs") or {}
            for name, value in inputs.items():
                link = _as_link(value)
                if link and link[0] == source_id and link[1] == output_slot:
                    found.append((str(node_id), str(name)))
        return found

    def apply_size_and_prompts(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        width: int,
        height: int,
    ) -> None:
        """Write snapped latent size and dialect prompts onto the base txt2img nodes.

        Must run before FaceDetailer injection so extra CLIP encodes are not
        mistaken for the KSampler pair.
        """
        latent_id = self.require_one("EmptyLatentImage")
        self.graph[latent_id]["inputs"]["width"] = int(width)
        self.graph[latent_id]["inputs"]["height"] = int(height)
        encodes = self.node_ids_of("CLIPTextEncode")
        if len(encodes) < 2:
            raise ComfyGraphError("base graph needs positive and negative CLIPTextEncode nodes")
        self.graph[encodes[0]]["inputs"]["text"] = str(prompt)
        self.graph[encodes[1]]["inputs"]["text"] = str(negative_prompt)

    def set_link(self, node_id: str, input_name: str, source_id: str, output_slot: int) -> None:
        node = self.graph.get(str(node_id))
        if node is None:
            raise ComfyGraphError(f"cannot rewire missing node {node_id!r}")
        inputs = node.setdefault("inputs", {})
        inputs[str(input_name)] = [str(source_id), int(output_slot)]

    def inject_conditioning_node(
        self,
        class_type: str,
        extra_inputs: dict[str, Any] | None = None,
        *,
        positive_input: str = "positive",
        negative_input: str = "negative",
        positive_output_slot: int = 0,
        negative_output_slot: int = 1,
        sampler_id: str | None = None,
    ) -> str:
        """Insert a node on the CLIPTextEncode → KSampler conditioning edges.

        Reads the live ``positive`` / ``negative`` links on KSampler (do not
        assume they are still node ``2``/``3``), copies those arrays onto the
        new node, then points KSampler at the new node's outputs. Every other
        KSampler input key is left untouched.
        """
        sampler_id = str(sampler_id or self.require_one("KSampler"))
        sampler = self.graph[sampler_id]
        inputs = sampler.setdefault("inputs", {})
        pos = _as_link(inputs.get("positive"))
        neg = _as_link(inputs.get("negative"))
        if pos is None or neg is None:
            raise ComfyGraphError(
                f"KSampler {sampler_id!r} is missing positive/negative links"
            )
        new_inputs = copy.deepcopy(extra_inputs or {})
        new_inputs[positive_input] = list(pos)
        new_inputs[negative_input] = list(neg)
        new_id = self.add_node(class_type, new_inputs)
        # Sever CLIPTextEncode (or prior conditioner) → KSampler and rewire.
        inputs["positive"] = [new_id, int(positive_output_slot)]
        inputs["negative"] = [new_id, int(negative_output_slot)]
        return new_id

    def inject_face_detailer(
        self,
        *,
        prompt: str = "",
        negative_prompt: str = "",
        seed: int = 42,
        sampler: str = "euler",
        scheduler: str = "normal",
        force: bool = False,
    ) -> str | None:
        """If the prompt requests a human subject, splice FaceDetailer after VAEDecode.

        IMAGE path becomes VAEDecode → FaceDetailer → SaveImageWebsocket (or
        SaveImage). ``model`` / ``clip`` / ``vae`` pointers are the same
        CheckpointLoaderSimple sockets the base KSampler and VAEDecode use.
        """
        if not force and not prompt_requests_human_subject(prompt):
            return None
        ckpt_id = self.require_one("CheckpointLoaderSimple")
        decode_id = self.require_one("VAEDecode")
        sampler_id = self.require_one("KSampler")
        save_ids = [nid for nid, node in self.graph.items()
                    if node.get("class_type") in SAVE_NODE_TYPES]
        if not save_ids:
            raise ComfyGraphError("graph has no SaveImage / SaveImageWebsocket node")

        sampler_inputs = self.graph[sampler_id].get("inputs") or {}
        decode_vae = _as_link((self.graph[decode_id].get("inputs") or {}).get("vae"))
        vae_link = list(decode_vae) if decode_vae else [ckpt_id, 2]
        model_link = _as_link(sampler_inputs.get("model")) or [ckpt_id, 0]

        detector_id = self.add_node("UltralyticsDetectorProvider", {
            "model_name": FACE_DETAIL_MODEL,
        })
        # Dedicated CLIP encodes keep FaceDetailer from stealing KSampler's
        # conditioning objects, but they use the same checkpoint CLIP pointer.
        pos_clip = self.add_node("CLIPTextEncode", {
            "text": f"{prompt}, {FACE_DETAIL_POSITIVE}".strip(", "),
            "clip": [ckpt_id, 1],
        }, meta={"title": "FaceDetailer Positive"})
        neg_clip = self.add_node("CLIPTextEncode", {
            "text": f"{negative_prompt}, {FACE_DETAIL_NEGATIVE}".strip(", "),
            "clip": [ckpt_id, 1],
        }, meta={"title": "FaceDetailer Negative"})

        detailer_id = self.add_node("FaceDetailer", {
            "image": [decode_id, 0],
            "model": [str(model_link[0]), int(model_link[1])],
            "clip": [ckpt_id, 1],
            "vae": [str(vae_link[0]), int(vae_link[1])],
            "guide_size": 768,
            "guide_size_for": True,
            "max_size": 1024,
            "seed": int(seed),
            "steps": 18,
            "cfg": 5.5,
            "sampler_name": sampler,
            "scheduler": scheduler,
            "positive": [pos_clip, 0],
            "negative": [neg_clip, 0],
            "denoise": 0.30,
            "feather": 8,
            "noise_mask": True,
            "force_inpaint": True,
            "bbox_threshold": 0.35,
            "bbox_dilation": 10,
            "bbox_crop_factor": 3.0,
            "sam_detection_hint": "none",
            "sam_dilation": 0,
            "sam_threshold": 0.93,
            "sam_bbox_expansion": 0,
            "sam_mask_hint_threshold": 0.7,
            "sam_mask_hint_use_negative": "False",
            "drop_size": 10,
            "bbox_detector": [detector_id, 0],
            "wildcard": "",
            "cycle": 1,
        })

        for node_id, input_name in self.consumers_of(decode_id, 0):
            if node_id == detailer_id:
                continue
            if self.graph[node_id].get("class_type") in SAVE_NODE_TYPES:
                self.set_link(node_id, input_name, detailer_id, 0)
        return detailer_id

    def build_media_graph(
        self,
        *,
        prompt: str,
        negative_prompt: str = "",
        auto_face_detail: bool = True,
        seed: int = 42,
        sampler: str = "euler",
        scheduler: str = "normal",
    ) -> dict[str, Any]:
        """Apply Task 3 auto FaceDetailer, then return the API graph."""
        if auto_face_detail:
            self.inject_face_detailer(
                prompt=prompt,
                negative_prompt=negative_prompt,
                seed=seed,
                sampler=sampler,
                scheduler=scheduler,
            )
        return self.to_prompt()

    def to_prompt(self) -> dict[str, Any]:
        return copy.deepcopy(self.graph)


def build_txt2img_with_optional_face_detailer(
    *,
    prompt: str,
    negative_prompt: str = "",
    auto_face_detail: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    builder = ComfyGraphBuilder.from_txt2img(
        prompt=prompt, negative_prompt=negative_prompt, **kwargs,
    )
    return builder.build_media_graph(
        prompt=prompt,
        negative_prompt=negative_prompt,
        auto_face_detail=auto_face_detail,
        seed=int(kwargs.get("seed", 42)),
        sampler=str(kwargs.get("sampler", "euler")),
        scheduler=str(kwargs.get("scheduler", "normal")),
    )
