"""Still-then-I2V helpers: load policy/graphs, run generate_until_accepted."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Callable

from .validate import load_fixture, missing_classes

ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location("_gvd_qa_runner", ROOT / "gvd_qa.py")
_RUNNER = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
import sys
sys.modules.setdefault("_gvd_qa_runner", _RUNNER)
_SPEC.loader.exec_module(_RUNNER)


def load_policy(path: Path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    policy = _RUNNER.policy_from_mapping(data)
    policy.validate()
    return policy


def bind_fast(filename: str, attempt_id: str, digest: str, policy, reference: str | None = None,
              local: bool = False):
    graph = load_fixture("fast_qa_local.api.json" if local else "fast_qa.api.json")
    graph = _RUNNER.bind_qa(graph, filename, attempt_id, digest, "90", policy.metrics_profile)
    if reference and "2" in graph:
        graph["2"]["inputs"]["image"] = reference
    elif not local:
        graph.pop("2", None)
        graph.pop("21", None)
        if "20" in graph:
            graph["20"]["inputs"].pop("Target_Image", None)
        graph["90"]["inputs"].pop("dino", None)
        graph["90"]["inputs"].pop("clip_image", None)
    return graph


def bind_qwen(filename: str, attempt_id: str, digest: str, policy, requirements_json: str,
              local: bool = False):
    graph = _RUNNER.bind_qa(
        load_fixture("qwen_qa_local.api.json" if local else "qwen_qa.api.json"),
        filename, attempt_id, digest,
        "91", policy.qwen_profile)
    graph["91"]["inputs"]["requirements_json"] = requirements_json
    return graph


def bind_reward(filename: str, attempt_id: str, digest: str, policy, caption: str = "",
                local: bool = False):
    graph = _RUNNER.bind_qa(
        load_fixture("reward_qa_local.api.json" if local else "reward_qa.api.json"),
        filename, attempt_id, digest,
        "92", policy.reward_profile)
    if caption:
        graph["92"]["inputs"]["text"] = caption
    return graph


def assert_graphs_activable(object_info: dict[str, Any] | None, graphs: list[dict]) -> None:
    if object_info is None:
        raise _RUNNER.QAError("object_info unavailable; cannot activate QA graphs")
    missing: list[str] = []
    for graph in graphs:
        missing.extend(missing_classes(graph, object_info))
    if missing:
        raise _RUNNER.QAError("QA graphs missing node classes: " + ",".join(sorted(set(missing))))


def run_still_qa(
    *,
    generation_graph: dict,
    seed_bindings: tuple[tuple[str, str], ...],
    generation_save_node: str,
    base_seed: int,
    expected_size: tuple[int, int],
    policy_path: Path,
    requirements_path: Path,
    phases,
    job_dir: Path,
    object_info: dict[str, Any] | None = None,
    resume: bool = False,
    wd14_aliases: dict[str, tuple[str, ...]] | None = None,
    record_evidence: Callable[..., None] | None = None,
    reference_upload: str | None = None,
    audit_caption: str = "",
    local: bool = False,
) -> Path:
    policy = load_policy(policy_path)
    requirements_json = Path(requirements_path).read_text(encoding="utf-8")
    sample_fast = bind_fast("x.png", "a", "0" * 64, policy, reference_upload, local=local)
    sample_qwen = bind_qwen("x.png", "a", "0" * 64, policy, requirements_json, local=local)
    sample_reward = bind_reward("x.png", "a", "0" * 64, policy, audit_caption, local=local)
    if not local:
        assert_graphs_activable(object_info, [generation_graph, sample_fast, sample_qwen, sample_reward])
    return _RUNNER.generate_until_accepted(
        generation_graph=generation_graph,
        seed_bindings=seed_bindings,
        generation_save_node=generation_save_node,
        base_seed=base_seed,
        expected_size=expected_size,
        policy=policy,
        requirements_json=requirements_json,
        make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, reference_upload, local=local),
        make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, requirements_json, local=local),
        make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, audit_caption, local=local),
        phases=phases,
        job_dir=job_dir,
        wd14_aliases=wd14_aliases,
        resume=resume,
        record_evidence=record_evidence,
    )


def run_persisted_still_qa(
    *,
    image: bytes,
    policy_path: Path,
    requirements_path: Path,
    phases,
    job_dir: Path,
    expected_size: tuple[int, int] | None = None,
    wd14_aliases: dict[str, tuple[str, ...]] | None = None,
    record_evidence: Callable[..., None] | None = None,
    audit_caption: str = "",
    local: bool = True,
    object_info: dict[str, Any] | None = None,
) -> Path:
    policy = load_policy(policy_path)
    requirements_json = Path(requirements_path).read_text(encoding="utf-8")
    if not local:
        assert_graphs_activable(object_info, [
            bind_fast("x.png", "a", "0" * 64, policy, None, local=False),
            bind_qwen("x.png", "a", "0" * 64, policy, requirements_json, local=False),
            bind_reward("x.png", "a", "0" * 64, policy, audit_caption, local=False),
        ])
    return _RUNNER.evaluate_persisted_candidate(
        image,
        policy=policy,
        requirements_json=requirements_json,
        make_fast_graph=lambda n, a, d: bind_fast(n, a, d, policy, None, local=local),
        make_qwen_graph=lambda n, a, d: bind_qwen(n, a, d, policy, requirements_json, local=local),
        make_reward_graph=lambda n, a, d: bind_reward(n, a, d, policy, audit_caption, local=local),
        phases=phases,
        job_dir=job_dir,
        wd14_aliases=wd14_aliases,
        record_evidence=record_evidence,
        expected_size=expected_size,
    )
