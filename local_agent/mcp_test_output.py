#!/usr/bin/env python3
"""Isolated ComfyUI output for live-verification / probe scripts only.

comfyui-mcp generate_image action:"image" hardcodes SaveImage
filename_prefix to "ComfyUI", so tools.comfy_generate cannot isolate a
test file from operator output. Probe scripts must enqueue their own
graph with SaveImage filename_prefix "mcp_test/<stem>" — ComfyUI treats
the slash as a subfolder under the shared output directory.

Not a TOOLS entry. Do not use this for operator-requested generation.
"""
from __future__ import annotations

import json
import re
import urllib.request
from typing import Any

MCP_TEST_SUBDIR = "mcp_test"
DEFAULT_URL = "http://127.0.0.1:8188"
_SAFE_STEM = re.compile(r"[^A-Za-z0-9._-]+")


def save_prefix(stem: str) -> str:
    """Return a SaveImage filename_prefix that lands under output/mcp_test/."""
    cleaned = _SAFE_STEM.sub("_", str(stem).strip()).strip("._-") or "probe"
    return f"{MCP_TEST_SUBDIR}/{cleaned}"


def build_txt2img_graph(
    *,
    prompt: str,
    checkpoint: str,
    filename_prefix: str,
    negative_prompt: str = "",
    width: int = 512,
    height: int = 512,
    steps: int = 8,
    cfg: float = 5.0,
    seed: int = 42,
    batch_size: int = 1,
    sampler: str = "euler",
    scheduler: str = "normal",
) -> dict[str, Any]:
    """Minimal txt2img graph matching comfyui-mcp's image composer, isolated prefix."""
    prefix = save_prefix(filename_prefix) if not str(filename_prefix).startswith(
        f"{MCP_TEST_SUBDIR}/"
    ) else str(filename_prefix)
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
            "inputs": {"width": width, "height": height, "batch_size": batch_size},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": seed,
                "steps": steps,
                "cfg": cfg,
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
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": prefix},
        },
    }


def enqueue_txt2img(
    *,
    url: str = DEFAULT_URL,
    timeout: int = 30,
    audit: bool = True,
    **params: Any,
) -> dict[str, Any]:
    """POST /prompt with an isolated mcp_test/ SaveImage graph. Optional audit JSONL."""
    prefix_stem = params.get("filename_prefix", "probe")
    graph = build_txt2img_graph(**params)
    prefix = graph["7"]["inputs"]["filename_prefix"]
    body = json.dumps({"prompt": graph, "client_id": "local_agent-mcp-test"}).encode("utf-8")
    req = urllib.request.Request(
        f"{url.rstrip('/')}/prompt",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        queued = json.loads(resp.read().decode("utf-8"))
    if audit:
        import tools
        tools._comfy_audit(
            "mcp_test_enqueue",
            "prompt",
            {
                "action": "image",
                "prompt": params.get("prompt"),
                "checkpoint": params.get("checkpoint"),
                "filename_prefix": prefix,
                "stem": prefix_stem,
            },
            {
                "risk": "generate",
                "mcp_status": "ok",
                "prompt_id": queued.get("prompt_id"),
                "caller": tools._comfy_caller(),
                "output_prefix": prefix,
            },
        )
    queued["filename_prefix"] = prefix
    return queued
