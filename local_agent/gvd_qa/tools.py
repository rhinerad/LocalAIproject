"""Whitelist-facing GVD QA tools."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

from .evaluate import evaluate_artifact
from .graph import attach_wd14_tagger, find_image_output_nodes
from .loop import next_seed, run_qa_loop

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("_gvd_qa_runner", _ROOT / "gvd_qa.py")
_RUNNER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
import sys as _sys
_sys.modules["_gvd_qa_runner"] = _RUNNER
_SPEC.loader.exec_module(_RUNNER)


def gvd_qa_evaluate(args: dict[str, Any] | None = None) -> str:
    args = args or {}
    history = args.get("history")
    graph = args.get("graph")
    if isinstance(history, str):
        history = json.loads(history)
    if isinstance(graph, str):
        graph = json.loads(graph)
    expected = args.get("expected_tags") or []
    if isinstance(expected, str):
        expected = [p.strip() for p in expected.split(",") if p.strip()]
    report = evaluate_artifact(
        prompt=str(args.get("prompt") or ""),
        artifact_path=args.get("artifact_path") or args.get("path"),
        history=history,
        graph=graph,
        expected_tags=expected,
        clip_min=float(args["clip_min"]) if args.get("clip_min") is not None else 0.22,
        require_vlm=bool(args.get("require_vlm")),
        vlm_caption=args.get("vlm_caption"),
        object_info=args.get("object_info"),
        installed_nodes=args.get("installed_nodes") or ("comfyui-wd14-tagger",),
    )
    if args.get("seed") is not None:
        report["next_seed"] = next_seed(int(args["seed"]), int(args.get("attempt") or 0))
    return json.dumps(report, indent=2)


def gvd_qa_attach_wd14(args: dict[str, Any]) -> str:
    graph = args.get("graph")
    if isinstance(graph, str):
        graph = json.loads(graph)
    if not isinstance(graph, dict):
        raise ValueError("graph must be an API node map")
    image_node = args.get("image_node_id")
    if not image_node:
        hits = find_image_output_nodes(graph)
        if not hits:
            raise ValueError("no IMAGE producer found; pass image_node_id")
        image_node = hits[0][0]
    attached = attach_wd14_tagger(graph, image_node_id=str(image_node))
    return json.dumps(attached, indent=2)


def gvd_qa_loop_tool(args: dict[str, Any]) -> str:
    """Offline/injected loop. A live Comfy render function is not implied."""
    renders = list(args.get("renders") or [])
    if not renders:
        raise ValueError("renders must be a list of {seed, history, graph, artifact_path, vlm_caption}")

    def render(seed: int) -> dict[str, Any]:
        for row in renders:
            if int(row.get("seed", -1)) == int(seed):
                return row
        return renders[min(len(renders) - 1, 0)]

    result = run_qa_loop(
        prompt=str(args.get("prompt") or ""),
        seed=int(args.get("seed") or renders[0].get("seed") or 0),
        render=render,
        attempt_budget=int(args.get("attempt_budget") or 3),
        expected_tags=args.get("expected_tags") or (),
        require_vlm=bool(args.get("require_vlm")),
        clip_min=float(args["clip_min"]) if args.get("clip_min") is not None else None,
    )
    return json.dumps(result, indent=2)


def gvd_qa_activation(args: dict[str, Any] | None = None) -> str:
    from .validate import qa_activation_report
    args = args or {}
    info = args.get("object_info") or {}
    if isinstance(info, str):
        info = json.loads(Path(info).read_text(encoding="utf-8"))
    return json.dumps(qa_activation_report(info), indent=2)


def gvd_qa_accepted_still(args: dict[str, Any]) -> str:
    receipt = Path(str(args.get("receipt") or args.get("qa_receipt") or ""))
    policy_id = str(args.get("policy_id") or "")
    rubric = str(args.get("requirements_sha256") or "")
    if args.get("requirements_json"):
        rubric = _RUNNER.sha256(Path(str(args["requirements_json"])).read_bytes())
    path = _RUNNER.accepted_i2v_image(receipt, policy_id, rubric)
    return json.dumps({"accepted": True, "image_path": str(path), "requirements_sha256": rubric}, indent=2)
