"""Fail-closed /object_info checks for QA graphs. Missing classes block activation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"

ADAPTER_CLASSES = {
    "GVDMetricReport", "GVDScoreCLIP", "GVDRewardReport",
    "GVDQwenChecklist", "GVDPromptPlan",
}
FAST_UPSTREAM = {"Clip_Score-\U0001f52c", "Dino_Score-\U0001f52c", "WD14Tagger|pysssss", "LoadImage"}
QWEN_UPSTREAM = {"LoadQwenVLMVerifier", "LoadImage"}
REWARD_UPSTREAM = {"LoadImageRewardVerifier", "LoadImage"}
PROMPT_UPSTREAM = {"PromptTester"}


def load_fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def missing_classes(graph: dict[str, Any], object_info: dict[str, Any] | None) -> list[str]:
    if not isinstance(object_info, dict):
        raise ValueError("object_info unavailable")
    missing = []
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        cls = str(node.get("class_type") or "")
        if cls and cls not in object_info:
            missing.append(cls)
    return sorted(set(missing))


def qa_activation_report(object_info: dict[str, Any] | None) -> dict[str, Any]:
    report = {"activable": False, "graphs": {}, "missing": []}
    if not isinstance(object_info, dict):
        report["missing"] = ["object_info"]
        return report
    for name in ("fast_qa.api.json", "qwen_qa.api.json", "reward_qa.api.json", "prompt_plan.api.json"):
        path = FIXTURES / name
        if not path.is_file():
            report["graphs"][name] = {"missing": [name]}
            continue
        graph = load_fixture(name)
        miss = missing_classes(graph, object_info)
        report["graphs"][name] = {"missing": miss, "ok": not miss}
        report["missing"].extend(miss)
    report["missing"] = sorted(set(report["missing"]))
    report["activable"] = not report["missing"]
    adapters_present = ADAPTER_CLASSES <= set(object_info)
    report["adapters_installed"] = adapters_present
    if not adapters_present:
        report["activable"] = False
        report["missing"] = sorted(set(report["missing"]) | (ADAPTER_CLASSES - set(object_info)))
    return report
