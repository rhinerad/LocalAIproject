"""Typed GVD registry contracts from gvd_tool_router_spec.md §3."""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

ToolName = Literal[
    "execute_narrative_scene", "execute_continuous_take",
    "execute_montage_morph", "execute_fast_action",
    "generate_still", "upscale_still", "synthesize_dialogue",
    "apply_lipsync", "repair_video",
]
PUBLIC_TOOL_NAMES: tuple[ToolName, ...] = (
    "execute_narrative_scene",
    "execute_continuous_take",
    "execute_montage_morph",
    "execute_fast_action",
)
Status = Literal[
    "discovered", "quarantined", "static_pass", "validation_pending",
    "validated", "active", "disabled", "rejected", "retired",
]
ContinuityMode = Literal["independent", "identity", "continuous", "morph"]
ACTIVE_REQUIRES = ("policy_receipt", "validation_report_sha256")

CAPABILITY_IDENTITY = "identity_reference"
CAPABILITY_FIRST_FRAME = "first_frame"
CAPABILITY_LAST_FRAME = "last_frame"
CAPABILITY_VIDEO_CONTEXT = "video_context"
CAPABILITY_AUDIO_CONDITIONING = "audio_conditioning"
CAPABILITY_NATIVE_AUDIO = "native_audio_output"
CAPABILITY_NARRATIVE = "narrative_identity"
CAPABILITY_CONTINUATION = "video_continuation"
CAPABILITY_MONTAGE = "montage_morph"
CAPABILITY_FAST = "fast_action"
CAPABILITY_STILL = "still_generation"
CAPABILITY_TTS = "tts"
CAPABILITY_LIPSYNC = "lipsync"
CAPABILITY_INPAINT = "video_inpainting"
# A reference clip whose pose/timing the new clip must follow, with a
# different character in it. Not continuation context (video_context):
# nothing from the reference is kept in the output. 2026-09-25q.
CAPABILITY_MOTION_REFERENCE = "motion_reference"


def require_sha256(value: str, *, field_name: str = "sha256") -> str:
    text = str(value).strip().lower()
    if not SHA256_RE.fullmatch(text):
        raise ValueError(f"{field_name} must be 64 hexadecimal characters")
    return text


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def sha256_json(data: Any) -> str:
    return sha256_bytes(canonical_json(data).encode("utf-8"))


@dataclass(frozen=True)
class ArtifactRef:
    asset_id: str
    sha256: str
    media_type: str

    def __post_init__(self) -> None:
        require_sha256(self.sha256)
        if not str(self.asset_id).strip():
            raise ValueError("asset_id is required")


@dataclass(frozen=True)
class CharacterState:
    character_id: str
    revision: str
    face_refs: tuple[ArtifactRef, ...]
    wardrobe_refs: tuple[ArtifactRef, ...]
    wardrobe_description: str
    props: tuple[str, ...]
    screen_position: str
    pose: str
    expression: str


@dataclass(frozen=True)
class ShotManifest:
    shot_id: str
    script_intent: str
    camera_motion: str
    character_state: tuple[CharacterState, ...]
    continuity_mode: ContinuityMode
    duration_s: float
    width: int
    height: int
    fps_num: int
    fps_den: int
    hard_requirements: frozenset[str]
    priorities: dict[str, float]
    dependencies: tuple[str, ...] = ()
    start_frame: ArtifactRef | None = None
    end_frame: ArtifactRef | None = None
    context_video: ArtifactRef | None = None
    audio: ArtifactRef | None = None
    motion_reference_video: ArtifactRef | None = None
    prompt_keyframes: tuple[tuple[int, str], ...] = ()
    allowed_degradations: frozenset[str] = frozenset()
    seed: int = 0
    duration_tolerance_s: float = 0.25
    inferred_confidence: dict[str, float] = field(default_factory=dict)
    evidence_spans: dict[str, str] = field(default_factory=dict)
    project_id: str = "default"
    # Operator engine policy (2026-09-26b). None means "MiniMax first, Wan
    # only as an announced last resort". "wan" records that the operator's
    # own request named Wan; the router then honours it and labels the
    # decision ENGINE_EXPLICIT_WAN instead of ENGINE_FALLBACK_WAN.
    requested_engine: str | None = None


@dataclass(frozen=True)
class InputParameter:
    name: str
    json_schema: dict[str, Any]
    required: bool
    default: Any = None


@dataclass(frozen=True)
class InputBinding:
    parameter: str
    node_id: str
    node_input: str
    transform: str = "identity"


@dataclass(frozen=True)
class OutputBinding:
    name: str
    node_id: str
    history_key: str
    media_type: str


@dataclass(frozen=True)
class Dependency:
    kind: Literal["comfy_core", "custom_node", "model", "python", "binary"]
    name: str
    source_url: str
    revision: str
    sha256: str | None
    license_id: str | None
    license_evidence_url: str | None

    def __post_init__(self) -> None:
        if self.sha256 is not None:
            require_sha256(self.sha256, field_name=f"{self.name}.sha256")
        if "/" in str(self.revision) or str(self.revision).lower() in {"main", "master", "latest", "head"}:
            raise ValueError(f"{self.name} revision must be an immutable commit/model id")


@dataclass(frozen=True)
class RuntimeLock:
    os: str
    python_version: str
    comfy_commit: str
    node_schema_sha256: str
    torch_version: str
    cuda_runtime: str
    driver_version: str
    gpu_name: str
    compute_capability: str
    attention_backend: str
    environment_sha256: str

    def __post_init__(self) -> None:
        require_sha256(self.node_schema_sha256, field_name="node_schema_sha256")
        require_sha256(self.environment_sha256, field_name="environment_sha256")


@dataclass(frozen=True)
class ResourceProfile:
    profile_id: str
    runtime_lock_sha256: str
    workload_sha256: str
    precision: str
    offload_mode: str
    peak_gpu_mib: int | None
    peak_host_ram_mib: int | None
    model_disk_mib: int | None
    cold_seconds: float | None
    warm_seconds: float | None
    evidence: Literal["unknown", "upstream_claim", "community_report", "local"]
    samples: int = 0
    report_uri: str | None = None

    def __post_init__(self) -> None:
        require_sha256(self.runtime_lock_sha256, field_name="runtime_lock_sha256")
        require_sha256(self.workload_sha256, field_name="workload_sha256")
        if self.peak_gpu_mib == 0:
            raise ValueError("unknown memory is never interpreted as zero")


@dataclass(frozen=True)
class WorkflowTemplate:
    relative_path: str
    sha256: str
    format: Literal["comfy_api"]
    node_types: tuple[str, ...]
    inputs: tuple[InputParameter, ...]
    bindings: tuple[InputBinding, ...]
    outputs: tuple[OutputBinding, ...]
    model_family_key: str

    def __post_init__(self) -> None:
        require_sha256(self.sha256)
        if self.format != "comfy_api":
            raise ValueError("only comfy_api templates are executable")


@dataclass(frozen=True)
class WorkflowStage:
    stage_id: str
    template: WorkflowTemplate
    depends_on: tuple[str, ...]
    input_sources: dict[str, str]


@dataclass(frozen=True)
class ToolImplementation:
    schema_version: int
    tool_name: ToolName
    implementation_id: str
    version: str
    status: Status
    capabilities: frozenset[str]
    limits: dict[str, Any]
    dependencies: tuple[Dependency, ...]
    runtime: RuntimeLock
    stages: tuple[WorkflowStage, ...]
    profiles: tuple[ResourceProfile, ...]
    quality_scores: dict[str, float]
    fallback_ids: tuple[str, ...]
    provenance_urls: tuple[str, ...]
    policy_receipt: str | None
    validation_report_sha256: str | None
    local_only: bool = True
    disabled_reason: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")
        if self.validation_report_sha256:
            require_sha256(self.validation_report_sha256, field_name="validation_report_sha256")
        _assert_acyclic(self.stages)
        _assert_fallback_not_self(self)

    def peak_unknown(self) -> bool:
        local = [p for p in self.profiles if p.evidence == "local"]
        if not local:
            return True
        return any(p.peak_gpu_mib is None for p in local)


@dataclass(frozen=True)
class ExecutionResult:
    shot_id: str
    attempt_id: str
    registry_digest: str
    implementation_id: str
    profile_id: str
    prompt_ids: tuple[str, ...]
    status: Literal["accepted", "retryable", "blocked", "failed"]
    artifacts: tuple[ArtifactRef, ...]
    actual_frames: int
    actual_fps_num: int
    actual_fps_den: int
    quality_report: str
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        require_sha256(self.registry_digest, field_name="registry_digest")


@dataclass(frozen=True)
class RouteDecision:
    status: Literal["selected", "blocked", "needs_manifest_review"]
    tool_name: ToolName | None
    implementation_id: str | None
    profile_id: str | None
    registry_digest: str
    stage_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    rejection_log: tuple[dict[str, Any], ...]
    score: float | None = None
    discovery_requested: bool = False
    # Engine policy annotations (2026-09-26b). ``engine`` is the winner's
    # family ("minimax" | "wan" | "other"). ``engine_selection`` says why
    # it won: "default" (MiniMax-first ranking, or a non-Wan family when no
    # MiniMax row fit), "explicit_request" (manifest.requested_engine ==
    # "wan"), "fallback" (MiniMax did not fit and Wan was the only fit), or
    # "requested_engine_unavailable". ``operator_notice`` is the plain
    # sentence the operator must see whenever Wan won without being asked.
    engine: str | None = None
    engine_selection: str | None = None
    operator_notice: str | None = None


def _assert_acyclic(stages: tuple[WorkflowStage, ...]) -> None:
    ids = {stage.stage_id for stage in stages}
    incoming = {stage.stage_id: set(stage.depends_on) for stage in stages}
    for stage in stages:
        for dep in stage.depends_on:
            if dep not in ids:
                raise ValueError(f"stage {stage.stage_id} depends on missing {dep}")
        for source in stage.input_sources.values():
            if source.startswith("manifest."):
                continue
            if "." not in source:
                raise ValueError(f"unresolvable input source {source}")
            other, _name = source.split(".", 1)
            if other not in ids and other != "manifest":
                raise ValueError(f"input source {source} does not resolve")
    remaining = set(ids)
    while remaining:
        ready = [sid for sid in remaining if incoming[sid].isdisjoint(remaining)]
        if not ready:
            raise ValueError("stage graph contains a cycle")
        remaining.difference_update(ready)


def _assert_fallback_not_self(impl: ToolImplementation) -> None:
    if impl.implementation_id in impl.fallback_ids:
        raise ValueError("fallback cycle: implementation lists itself")


def to_plain(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {k: to_plain(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_plain(v) for v in value]
    if isinstance(value, frozenset):
        return sorted(to_plain(v) for v in value)
    return value


def _engine(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    return text or None


def _artifact(data: dict[str, Any] | None) -> ArtifactRef | None:
    if not data:
        return None
    return ArtifactRef(**data)


def shot_from_dict(data: dict[str, Any]) -> ShotManifest:
    characters = []
    for row in data.get("character_state") or []:
        characters.append(CharacterState(
            character_id=row["character_id"],
            revision=row["revision"],
            face_refs=tuple(ArtifactRef(**r) for r in row.get("face_refs") or []),
            wardrobe_refs=tuple(ArtifactRef(**r) for r in row.get("wardrobe_refs") or []),
            wardrobe_description=row.get("wardrobe_description", ""),
            props=tuple(row.get("props") or ()),
            screen_position=row.get("screen_position", ""),
            pose=row.get("pose", ""),
            expression=row.get("expression", ""),
        ))
    kf = tuple((int(a), str(b)) for a, b in data.get("prompt_keyframes") or ())
    return ShotManifest(
        shot_id=str(data["shot_id"]),
        script_intent=str(data.get("script_intent") or ""),
        camera_motion=str(data.get("camera_motion") or ""),
        character_state=tuple(characters),
        continuity_mode=data.get("continuity_mode") or "independent",
        duration_s=float(data["duration_s"]),
        width=int(data["width"]),
        height=int(data["height"]),
        fps_num=int(data.get("fps_num") or 24),
        fps_den=int(data.get("fps_den") or 1),
        hard_requirements=frozenset(data.get("hard_requirements") or ()),
        priorities=dict(data.get("priorities") or {}),
        dependencies=tuple(data.get("dependencies") or ()),
        start_frame=_artifact(data.get("start_frame")),
        end_frame=_artifact(data.get("end_frame")),
        context_video=_artifact(data.get("context_video")),
        audio=_artifact(data.get("audio")),
        motion_reference_video=_artifact(data.get("motion_reference_video")),
        prompt_keyframes=kf,
        allowed_degradations=frozenset(data.get("allowed_degradations") or ()),
        seed=int(data.get("seed") or 0),
        duration_tolerance_s=float(data.get("duration_tolerance_s") or 0.25),
        inferred_confidence=dict(data.get("inferred_confidence") or {}),
        evidence_spans=dict(data.get("evidence_spans") or {}),
        project_id=str(data.get("project_id") or "default"),
        requested_engine=_engine(data.get("requested_engine")),
    )


def _param(data: dict[str, Any]) -> InputParameter:
    return InputParameter(
        name=data["name"],
        json_schema=dict(data.get("json_schema") or {}),
        required=bool(data.get("required")),
        default=data.get("default"),
    )


def _binding(data: dict[str, Any]) -> InputBinding:
    return InputBinding(
        parameter=data["parameter"],
        node_id=str(data["node_id"]),
        node_input=str(data["node_input"]),
        transform=str(data.get("transform") or "identity"),
    )


def _output(data: dict[str, Any]) -> OutputBinding:
    return OutputBinding(
        name=data["name"],
        node_id=str(data["node_id"]),
        history_key=str(data["history_key"]),
        media_type=str(data["media_type"]),
    )


def _template(data: dict[str, Any]) -> WorkflowTemplate:
    return WorkflowTemplate(
        relative_path=data["relative_path"],
        sha256=data["sha256"],
        format=data.get("format") or "comfy_api",
        node_types=tuple(data.get("node_types") or ()),
        inputs=tuple(_param(p) for p in data.get("inputs") or ()),
        bindings=tuple(_binding(b) for b in data.get("bindings") or ()),
        outputs=tuple(
            _output(o)
            for o in (
                [data["outputs"]]
                if isinstance(data.get("outputs"), dict)
                else (data.get("outputs") or ())
            )
        ),
        model_family_key=str(data["model_family_key"]),
    )


def implementation_from_dict(data: dict[str, Any]) -> ToolImplementation:
    runtime = RuntimeLock(**data["runtime"])
    stages = tuple(
        WorkflowStage(
            stage_id=row["stage_id"],
            template=_template(row["template"]),
            depends_on=tuple(row.get("depends_on") or ()),
            input_sources=dict(row.get("input_sources") or {}),
        )
        for row in data.get("stages") or ()
    )
    profiles = tuple(ResourceProfile(**row) for row in data.get("profiles") or ())
    deps = tuple(Dependency(**row) for row in data.get("dependencies") or ())
    return ToolImplementation(
        schema_version=int(data.get("schema_version") or 1),
        tool_name=data["tool_name"],
        implementation_id=data["implementation_id"],
        version=str(data["version"]),
        status=data["status"],
        capabilities=frozenset(data.get("capabilities") or ()),
        limits=dict(data.get("limits") or {}),
        dependencies=deps,
        runtime=runtime,
        stages=stages,
        profiles=profiles,
        quality_scores=dict(data.get("quality_scores") or {}),
        fallback_ids=tuple(data.get("fallback_ids") or ()),
        provenance_urls=tuple(data.get("provenance_urls") or ()),
        policy_receipt=data.get("policy_receipt"),
        validation_report_sha256=data.get("validation_report_sha256"),
        local_only=bool(data.get("local_only", True)),
        disabled_reason=data.get("disabled_reason"),
    )


def can_activate(impl: ToolImplementation) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if impl.status not in {"validated", "active"}:
        reasons.append("status_not_validated")
    if not impl.policy_receipt:
        reasons.append("missing_policy_receipt")
    if not impl.validation_report_sha256:
        reasons.append("missing_validation_report")
    if not impl.dependencies:
        reasons.append("missing_dependencies")
    local_profiles = [
        p for p in impl.profiles
        if p.evidence == "local" and p.peak_gpu_mib is not None
    ]
    if not local_profiles:
        reasons.append("missing_local_resource_profile")
    if impl.peak_unknown():
        reasons.append("unknown_vram")
    return (not reasons), reasons
