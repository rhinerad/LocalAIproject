"""Compose CLIP / ImageReward / Qwen-VL / WD14 / Caption V4 into one gate."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from .ablation import ignored_keywords
from .constants import (
    ADAPTER_PROMPT_TESTER,
    ADAPTER_WD14,
    ADAPTER_WU,
    ADAPTER_YRIKKA,
    DEFAULT_CLIP_MIN,
    DEFAULT_IMAGE_REWARD_MIN,
    DEFAULT_VLM_ALIGNMENT_MIN,
)
from .duplicate import detect_duplicates
from .parse import parse_verifier_outputs

VLM_MODEL = "qwen25-vl-nsfw-caption:v4-q4_k_m"
VLM_RUNTIME = "llama.cpp"


def _norm_tag(text: str) -> str:
    return " ".join(str(text).lower().replace("_", " ").split())


def evaluate_artifact(
    *,
    prompt: str,
    artifact_path: str | Path | None = None,
    history: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    expected_tags: Iterable[str] = (),
    clip_min: float = DEFAULT_CLIP_MIN,
    image_reward_min: float = DEFAULT_IMAGE_REWARD_MIN,
    vlm_alignment_min: float = DEFAULT_VLM_ALIGNMENT_MIN,
    require_vlm: bool = False,
    object_info: dict[str, Any] | None = None,
    vlm_parser: Callable[..., dict[str, Any]] | None = None,
    vlm_caption: str | None = None,
    installed_nodes: Iterable[str] = (),
    artifact_bytes: bytes | None = None,
    prior_artifacts: Iterable[tuple[str, str | Path | None]] = (),
) -> dict[str, Any]:
    """Fail-closed QA report. Missing required VLM identity is a fail."""
    parsed = parse_verifier_outputs(history, graph=graph)
    classes = set(object_info or {})
    installed = {str(x) for x in installed_nodes}

    adapters = {
        ADAPTER_YRIKKA: "installed" if any("QwenVLM" in c.replace(" ", "") or "ImageReward" in c for c in classes) else "adapter_required",
        ADAPTER_WU: "installed" if any("DINO" in c.upper() for c in classes) else "adapter_required",
        ADAPTER_PROMPT_TESTER: "adapter_required",
        ADAPTER_WD14: "installed" if (
            "WD14Tagger|pysssss" in classes
            or ADAPTER_WD14 in installed
            or "comfyui-wd14-tagger" in {x.lower() for x in installed}
        ) else "missing",
    }

    reasons: list[str] = []
    qwen_vl = parsed.get("qwen_vl")
    clip_score = parsed.get("clip_score")
    image_reward = parsed.get("image_reward")
    tags = list(parsed.get("wd14_tags") or [])

    if qwen_vl is False:
        reasons.append("qwen_vl_verifier_false")
    if clip_score is not None and float(clip_score) < float(clip_min):
        reasons.append("clip_score_below_threshold")
    if image_reward is not None and float(image_reward) < float(image_reward_min):
        reasons.append("image_reward_below_threshold")

    missing_required: list[str] = []
    tag_blob = " ".join(_norm_tag(t) for t in tags)
    for expected in expected_tags:
        needle = _norm_tag(expected)
        if needle and needle not in tag_blob:
            missing_required.append(needle)
    if missing_required:
        reasons.append("wd14_missing_required_tags")

    vlm_report: dict[str, Any] | None = None
    if vlm_caption is not None:
        if vlm_parser is None:
            try:
                from media_accuracy_gate import parse_video_director_scores
                vlm_parser = parse_video_director_scores
            except Exception:
                vlm_parser = None
        if vlm_parser is None:
            reasons.append("vlm_parser_unavailable")
        else:
            vlm_report = vlm_parser(
                vlm_caption,
                prompt,
                model=VLM_MODEL,
                runtime=VLM_RUNTIME,
            )
            if vlm_report.get("status") != "pass":
                reasons.append("caption_v4_parse_failed")
            scores = vlm_report.get("scores") or {}
            alignment = scores.get("text_video_alignment")
            if alignment is not None and float(alignment) < float(vlm_alignment_min):
                reasons.append("caption_v4_alignment_below_threshold")
    elif require_vlm:
        reasons.append("caption_v4_required_but_missing")

    dup_report: dict[str, Any] = {"duplicate": False, "reasons": [], "evidence": []}
    if prior_artifacts:
        candidate_caption = vlm_caption or " ".join(tags)
        dup_report = detect_duplicates(
            candidate_image=artifact_bytes,
            candidate_path=artifact_path,
            candidate_caption=candidate_caption,
            prior=prior_artifacts,
        )
        for dup_reason in dup_report.get("reasons") or []:
            reasons.append(dup_reason)

    # Fix 2026-09-23 (readiness-audit finding 1.2): this function was
    # fail-open. With require_vlm=False (the default) and no history/graph
    # verifier scores, a candidate with a missing or empty artifact_path --
    # or with literally no evidence supplied at all -- returned
    # passed=True/action="accept". Reproduced: a nonexistent MP4 path with
    # no other evidence passed. Both gaps are closed here without changing
    # any of the existing threshold/reroll behavior above.
    artifact_missing = False
    if artifact_path is not None:
        try:
            ap = Path(artifact_path)
            artifact_missing = (not ap.is_file()) or ap.stat().st_size == 0
        except OSError:
            artifact_missing = True
        if artifact_missing:
            reasons.append("artifact_missing_or_unreadable")
    has_any_evidence = (
        qwen_vl is not None
        or clip_score is not None
        or image_reward is not None
        or bool(tags)
        or vlm_report is not None
        or (artifact_path is not None and not artifact_missing)
    )
    if not has_any_evidence:
        reasons.append("no_qa_evidence")

    ignored = ignored_keywords(prompt, tags)
    action = "accept"
    if reasons:
        action = "reroll" if any(
            r in reasons for r in (
                "qwen_vl_verifier_false",
                "clip_score_below_threshold",
                "caption_v4_alignment_below_threshold",
                "wd14_missing_required_tags",
            )
        ) else "hold_review"

    path = str(artifact_path) if artifact_path else None
    return {
        "passed": not reasons,
        "action": action if reasons else "accept",
        "reasons": reasons,
        "scores": {
            "qwen_vl": qwen_vl,
            "clip_score": clip_score,
            "image_reward": image_reward,
            "dino_score": parsed.get("dino_score"),
            "caption_v4": None if vlm_report is None else vlm_report.get("scores"),
        },
        "wd14_tags": tags,
        "missing_required_tags": missing_required,
        "ignored_keywords": ignored,
        "duplicate": dup_report,
        "adapters": adapters,
        "artifact_path": path,
        "prompt": prompt,
        "note": (
            "Automatic metrics nominate failures; they do not certify human quality. "
            "YRIKKA/wu12023/PromptTester stay out of the 16GB Comfy process."
        ),
    }
