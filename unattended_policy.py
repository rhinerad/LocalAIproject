#!/usr/bin/env python3
"""Job-scoped unattended acceptance policy for GVD production."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


class UnattendedPolicyError(RuntimeError):
    pass


@dataclass
class UnattendedPolicy:
    """Explicit unattended rules; never silently drop historical operator gates globally."""

    job_id: str
    require_technical_qa: bool = True
    require_audio_qa_when_dialogue: bool = True
    require_selected_artifacts: bool = True
    max_retries_per_shot: int = 3
    max_replans_per_shot: int = 2
    max_wall_clock_s: float | None = None
    max_vram_mib: int | None = 15500
    allow_editorial_fallback: bool = False
    native_minimax_voice_required: bool = True
    allow_tts_alternate_backend: bool = False
    calibrated_thresholds: dict[str, float] = field(
        default_factory=lambda: {
            "voice_similarity_min": 0.55,
            "transcript_exact": 1.0,
            "identity_similarity_min": 0.50,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "UnattendedPolicy":
        return cls(
            job_id=str(obj["job_id"]),
            require_technical_qa=bool(obj.get("require_technical_qa", True)),
            require_audio_qa_when_dialogue=bool(obj.get("require_audio_qa_when_dialogue", True)),
            require_selected_artifacts=bool(obj.get("require_selected_artifacts", True)),
            max_retries_per_shot=int(obj.get("max_retries_per_shot", 3)),
            max_replans_per_shot=int(obj.get("max_replans_per_shot", 2)),
            max_wall_clock_s=(
                float(obj["max_wall_clock_s"]) if obj.get("max_wall_clock_s") is not None else None
            ),
            max_vram_mib=(int(obj["max_vram_mib"]) if obj.get("max_vram_mib") is not None else None),
            allow_editorial_fallback=bool(obj.get("allow_editorial_fallback", False)),
            native_minimax_voice_required=bool(obj.get("native_minimax_voice_required", True)),
            allow_tts_alternate_backend=bool(obj.get("allow_tts_alternate_backend", False)),
            calibrated_thresholds=dict(obj.get("calibrated_thresholds") or {}),
        )

    def save(self, path: Path | str) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "UnattendedPolicy":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


@dataclass
class AcceptanceRecord:
    """Separate machine vs operator acceptance — do not conflate."""

    job_id: str
    shot_id: str
    attempt_id: str
    machine_accepted: bool = False
    operator_accepted: bool | None = None
    machine_reasons: list[str] = field(default_factory=list)
    operator_reasons: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def is_fully_accepted(self, *, require_operator: bool) -> bool:
        if not self.machine_accepted:
            return False
        if require_operator and self.operator_accepted is not True:
            return False
        return True


def evaluate_machine_acceptance(
    policy: UnattendedPolicy,
    *,
    technical_pass: bool,
    audio_pass: bool | None,
    has_dialogue: bool,
    selected: bool,
    retry_count: int,
    replan_count: int,
    voice_backend: str | None = None,
    metrics: Mapping[str, float] | None = None,
) -> AcceptanceRecord:
    reasons: list[str] = []
    metrics = dict(metrics or {})
    if policy.require_technical_qa and not technical_pass:
        reasons.append("technical_qa_failed")
    if policy.require_audio_qa_when_dialogue and has_dialogue and audio_pass is not True:
        reasons.append("audio_qa_failed")
    if policy.require_selected_artifacts and not selected:
        reasons.append("not_selected")
    if retry_count > policy.max_retries_per_shot:
        reasons.append("retry_budget_exceeded")
    if replan_count > policy.max_replans_per_shot:
        reasons.append("replan_budget_exceeded")
    if policy.native_minimax_voice_required and not policy.allow_tts_alternate_backend:
        b = str(voice_backend or "").lower()
        if b in {"f5", "f5-tts", "fish", "fish_audio", "local_f5"}:
            reasons.append("tts_backend_forbidden_under_native_policy")
    for key, vmin in (policy.calibrated_thresholds or {}).items():
        if key in metrics and float(metrics[key]) < float(vmin):
            reasons.append(f"threshold:{key}")
    ok = not reasons
    return AcceptanceRecord(
        job_id=policy.job_id,
        shot_id="",
        attempt_id="",
        machine_accepted=ok,
        machine_reasons=reasons,
        metrics=dict(metrics),
    )


def assert_incomplete_job_not_claimed(
    *,
    required_shots: list[str],
    selected_shots: list[str],
    exhausted_shots: list[str],
) -> None:
    missing = [s for s in required_shots if s not in selected_shots]
    if missing:
        raise UnattendedPolicyError(
            f"incomplete job; missing SELECTED shots={missing}; exhausted={exhausted_shots}"
        )
