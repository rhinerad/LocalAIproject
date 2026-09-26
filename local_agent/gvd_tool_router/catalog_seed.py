"""Initial catalog: all four public tools exist; implementations start disabled."""
from __future__ import annotations

import json
from pathlib import Path

from .paths import GvdLayout, SCHEMA_VERSION
from .schema import (
    CAPABILITY_CONTINUATION,
    CAPABILITY_FAST,
    CAPABILITY_FIRST_FRAME,
    CAPABILITY_IDENTITY,
    CAPABILITY_LAST_FRAME,
    CAPABILITY_MONTAGE,
    CAPABILITY_NARRATIVE,
    CAPABILITY_STILL,
    CAPABILITY_TTS,
    CAPABILITY_LIPSYNC,
    CAPABILITY_INPAINT,
    CAPABILITY_MOTION_REFERENCE,
    CAPABILITY_VIDEO_CONTEXT,
    Dependency,
    InputBinding,
    InputParameter,
    OutputBinding,
    PUBLIC_TOOL_NAMES,
    ResourceProfile,
    RuntimeLock,
    ToolImplementation,
    WorkflowStage,
    WorkflowTemplate,
    sha256_bytes,
    sha256_json,
    to_plain,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
KNOWN_GOOD_GRAPH = FIXTURES / "known_good_still.api.json"

UNKNOWN_SHA = "0" * 64


def placeholder_runtime() -> RuntimeLock:
    return RuntimeLock(
        os="Windows",
        python_version="3.12",
        comfy_commit="unmeasured",
        node_schema_sha256=UNKNOWN_SHA,
        torch_version="unmeasured",
        cuda_runtime="unmeasured",
        driver_version="unmeasured",
        gpu_name="NVIDIA GeForce RTX 5080",
        compute_capability="unmeasured",
        attention_backend="installed_pytorch_default",
        environment_sha256=UNKNOWN_SHA,
    )


def _dep(name: str, url: str, revision: str) -> Dependency:
    return Dependency(
        kind="custom_node",
        name=name,
        source_url=url,
        revision=revision,
        sha256=None,
        license_id=None,
        license_evidence_url=None,
    )


def _empty_stage(stage_id: str, family: str) -> WorkflowStage:
    template = WorkflowTemplate(
        relative_path="pending.json",
        sha256=UNKNOWN_SHA,
        format="comfy_api",
        node_types=(),
        inputs=(),
        bindings=(),
        outputs=(),
        model_family_key=family,
    )
    return WorkflowStage(stage_id=stage_id, template=template, depends_on=(), input_sources={})


def _disabled(
    tool_name: str,
    implementation_id: str,
    capabilities: set[str],
    *,
    family: str,
    reason: str,
    provenance: tuple[str, ...] = (),
    fallbacks: tuple[str, ...] = (),
    extra_limits: dict | None = None,
) -> ToolImplementation:
    return ToolImplementation(
        schema_version=SCHEMA_VERSION,
        tool_name=tool_name,  # type: ignore[arg-type]
        implementation_id=implementation_id,
        version="0.0.0-unvalidated",
        status="disabled",
        capabilities=frozenset(capabilities),
        limits=extra_limits or {},
        dependencies=(_dep(implementation_id, provenance[0] if provenance else "https://example.invalid", "unvalidated-pending"),),
        runtime=placeholder_runtime(),
        stages=(_empty_stage("stage0", family),),
        profiles=(),
        quality_scores={},
        fallback_ids=fallbacks,
        provenance_urls=provenance,
        policy_receipt=None,
        validation_report_sha256=None,
        local_only=True,
        disabled_reason=reason,
    )


def known_good_still_implementation(graph_bytes: bytes) -> ToolImplementation:
    graph = json.loads(graph_bytes.decode("utf-8"))
    digest = sha256_json(graph)
    node_types = tuple(str(n.get("class_type")) for n in graph.values())
    runtime = placeholder_runtime()
    runtime_sha = sha256_json(to_plain(runtime))
    workload = sha256_json({"width": 512, "height": 512, "steps": 1})
    template = WorkflowTemplate(
        relative_path=f"{digest}/workflow.api.json",
        sha256=digest,
        format="comfy_api",
        node_types=node_types,
        inputs=(
            InputParameter("prompt", {"type": "string"}, True),
            InputParameter("seed", {"type": "integer", "minimum": 0}, False, 0),
        ),
        bindings=(
            InputBinding("prompt", "2", "text"),
            InputBinding("seed", "5", "seed"),
        ),
        outputs=(
            OutputBinding("image", "7", "images", "image/png"),
        ),
        model_family_key="sdxl_txt2img",
    )
    profile = ResourceProfile(
        profile_id="local_smoke_512",
        runtime_lock_sha256=runtime_sha,
        workload_sha256=workload,
        precision="fp16",
        offload_mode="none",
        peak_gpu_mib=4096,
        peak_host_ram_mib=2048,
        model_disk_mib=None,
        cold_seconds=None,
        warm_seconds=None,
        evidence="local",
        samples=1,
        report_uri="fixture",
    )
    return ToolImplementation(
        schema_version=SCHEMA_VERSION,
        tool_name="generate_still",
        implementation_id="known_good_sdxl_txt2img_v1",
        version="1.0.0-m1",
        status="disabled",
        capabilities=frozenset({CAPABILITY_STILL}),
        limits={"width": [512], "height": [512], "max_refs": 0},
        dependencies=(
            Dependency(
                kind="model",
                name="RealVisXL_V5.0_fp16.safetensors",
                source_url="local",
                revision="on-disk-unhashed",
                sha256=None,
                license_id=None,
                license_evidence_url=None,
            ),
        ),
        runtime=runtime,
        stages=(
            WorkflowStage(
                stage_id="still",
                template=template,
                depends_on=(),
                input_sources={"prompt": "manifest.script_intent", "seed": "manifest.seed"},
            ),
        ),
        profiles=(profile,),
        quality_scores={"reliability": 1.0},
        fallback_ids=(),
        provenance_urls=("local_agent/comfy_api.py:build_txt2img_graph",),
        policy_receipt=None,
        validation_report_sha256=None,
        local_only=True,
        disabled_reason="awaiting M1 local execute receipt",
    )


def seed_implementations(graph_bytes: bytes | None = None) -> list[ToolImplementation]:
    graph_bytes = graph_bytes or KNOWN_GOOD_GRAPH.read_bytes()
    disabled_reason = "pending local validation; catalog row only"
    rows = [
        _disabled(
            "execute_narrative_scene",
            "storydiffusion_ipadapter_unvalidated",
            {CAPABILITY_NARRATIVE, CAPABILITY_IDENTITY, CAPABILITY_STILL},
            family="storydiffusion",
            reason=disabled_reason,
            provenance=("https://github.com/smthemex/ComfyUI_StoryDiffusion",),
        ),
        _disabled(
            "execute_narrative_scene",
            "ipadapter_sdxl_plus_face_unvalidated",
            {CAPABILITY_NARRATIVE, CAPABILITY_IDENTITY, CAPABILITY_STILL},
            family="ipadapter",
            reason=disabled_reason,
            provenance=("https://github.com/cubiq/ComfyUI_IPAdapter_plus",),
        ),
        _disabled(
            "execute_continuous_take",
            "wan22_i2v_q4_high_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT},
            family="wan",
            reason=disabled_reason,
            provenance=("https://github.com/kijai/ComfyUI-WanVideoWrapper",),
        ),
        _disabled(
            "execute_continuous_take",
            "wan22_i2v_q4_dual_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT},
            family="wan_dual",
            reason="Wan 2.2 I2V dual MoE high+low Q4 unmeasured",
            provenance=("https://github.com/kijai/ComfyUI-WanVideoWrapper",),
        ),
        _disabled(
            "execute_continuous_take",
            "wan22_i2v_8step_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_VIDEO_CONTEXT},
            family="wan_8step",
            reason="Wan 2.2 I2V eight-step; not yet measured on this GPU",
            provenance=("https://github.com/kijai/ComfyUI-WanVideoWrapper",),
            extra_limits={"steps": [8]},
        ),
        _disabled(
            "execute_continuous_take",
            "longcat_video_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_VIDEO_CONTEXT},
            family="longcat",
            reason=disabled_reason,
            provenance=("https://github.com/meituan-longcat/LongCat-Video",),
        ),
        _disabled(
            "execute_continuous_take",
            "minimax_h3_fl2va_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_FIRST_FRAME, CAPABILITY_LAST_FRAME},
            family="minimax_h3_fl2va",
            reason=disabled_reason,
            provenance=("https://github.com/MiniMax-AI/MiniMax-H3",),
        ),
        _disabled(
            "execute_continuous_take",
            "minimax_h3_ref2va_unvalidated",
            {CAPABILITY_CONTINUATION, CAPABILITY_IDENTITY, CAPABILITY_VIDEO_CONTEXT},
            family="minimax_h3_ref2va",
            reason="Ref2VA is a separate H3 variant; not interchangeable with FL2VA",
            provenance=("https://github.com/MiniMax-AI/awesome-minimax-h3-integration",),
        ),
        _disabled(
            "execute_montage_morph",
            "animatediff_fizz_unvalidated",
            {CAPABILITY_MONTAGE},
            family="animatediff_fizz",
            reason=disabled_reason,
            provenance=(
                "https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved",
                "https://github.com/FizzleDorf/ComfyUI_FizzNodes",
            ),
        ),
        _disabled(
            "execute_fast_action",
            "ltx23_unvalidated",
            {CAPABILITY_FAST},
            family="ltx23",
            reason=disabled_reason,
            provenance=("https://docs.comfy.org/tutorials/video/ltx/ltx-2-3",),
        ),
        _disabled(
            "execute_fast_action",
            "fasth3_v1_t2va_unvalidated",
            {CAPABILITY_FAST},
            family="fasth3_v1",
            reason="FastH3 Preview V1 is T2VA-only four-step; cannot accept FL2VA/Ref2VA",
            provenance=("https://haoailab.com/blogs/fasth3-preview/",),
            extra_limits={"modes": ["t2va"], "steps": [4], "ref2va": False, "fl2va": False},
        ),
        _disabled(
            "execute_fast_action",
            "fasth3_v2_unvalidated",
            {CAPABILITY_FAST, CAPABILITY_FIRST_FRAME, CAPABILITY_LAST_FRAME},
            family="fasth3_v2",
            reason="FastH3 V2 eight-step; T2V and FL I2V; no distilled Ref2VA",
            provenance=("https://docs.comfy.org/tutorials/video/minimax/minimax-h3-fastvideo",),
            # requires_operator_approval is enforced by router._compatible()
            # (2026-09-26b): without manifest operator_approved_resource_override
            # the row is rejected with operator_approval_required; with it the
            # 512 MiB approval headroom applies (peak 14,889 MiB, 16 GiB card).
            extra_limits={"modes": ["t2v", "fl_i2v"], "steps": [8], "ref2va": False, "requires_operator_approval": True},
        ),
        # Reference-video motion transfer with character replacement
        # (2026-09-25q; docs/REFERENCE_VIDEO_MOTION_TRANSFER_2026-09-25.md).
        # None is active: two need weights that are not on disk, the third has
        # every node and weight installed but no pinned template and no local
        # VRAM profile. Listed so gvd_route_shot can say exactly that instead
        # of a bare UNAVAILABLE_CAPABILITY.
        _disabled(
            "execute_narrative_scene",
            "wan22_animate_14b_unvalidated",
            {CAPABILITY_MOTION_REFERENCE, CAPABILITY_IDENTITY, CAPABILITY_NARRATIVE},
            family="wan22_animate",
            reason=("weights not on disk: Wan2.2-Animate-14B (~17 GB fp8 scaled, "
                    "diffusion_models/) and its relight LoRA (~0.6 GB, loras/); "
                    "WanVideoWrapper WanVideoAnimateEmbeds node code is installed; "
                    "umt5-xxl, Wan 2.1 VAE and clip_vision_h are present; "
                    "no local VRAM profile"),
            provenance=("https://huggingface.co/Wan-AI/Wan2.2-Animate-14B",
                        "https://huggingface.co/Kijai/WanVideo_comfy_fp8_scaled",
                        "https://github.com/kijai/ComfyUI-WanVideoWrapper"),
        ),
        _disabled(
            "execute_narrative_scene",
            "wan21_vace_1_3b_unvalidated",
            {CAPABILITY_MOTION_REFERENCE, CAPABILITY_IDENTITY, CAPABILITY_NARRATIVE},
            family="wan21_vace",
            reason=("weights not on disk: Wan2_1-VACE_module_1_3B_bf16 (~1.2 GB, "
                    "diffusion_models/); base wan2.1_t2v_1.3B_fp16 is present; "
                    "WanVideoWrapper WanVideoVACEEncode node code is installed; "
                    "no local VRAM profile"),
            provenance=("https://huggingface.co/Kijai/WanVideo_comfy",
                        "https://github.com/ali-vilab/VACE"),
        ),
        _disabled(
            "execute_narrative_scene",
            "animatediff_sdxl_pose_ipadapter_unvalidated",
            {CAPABILITY_MOTION_REFERENCE, CAPABILITY_IDENTITY, CAPABILITY_NARRATIVE},
            family="animatediff_sdxl_pose",
            reason=("every weight is installed (AnimateDiff-Evolved with mm_sdxl_v10_beta "
                    "/ hsxl_temporal_layers, controlnet-union-sdxl-1.0-promax, "
                    "ip-adapter-plus-face_sdxl_vit-h + CLIP-ViT-H, DWPose cached in "
                    "controlnet_aux) and one 16-frame window rendered live 2026-09-25; "
                    "its vertical inversion is root-caused (CHANGELOG 2026-09-25t: only when "
                    "DWPose draws face and hand keypoints together; detect_face=disable renders "
                    "upright and follows the reference motion); "
                    "the ComfyUI-Advanced-ControlNet node pack is installed (2026-09-25u) "
                    "and 24-frame multi-window clips render; identity holds with a "
                    "face-cropped reference (2026-09-25v); a video face-detail pass helps "
                    "late frames without flicker, faces stay soft at 768x448 (2026-09-26a); "
                    "FaceID Plus V2 in the detail pass raises identity similarity ~4x "
                    "(2026-09-26g); "
                    "no pinned API template and no local VRAM profile yet"),
            provenance=("https://github.com/Kosinkadink/ComfyUI-AnimateDiff-Evolved",
                        "https://github.com/Fannovel16/comfyui_controlnet_aux",
                        "https://github.com/cubiq/ComfyUI_IPAdapter_plus"),
        ),
        known_good_still_implementation(graph_bytes),
        _disabled(
            "synthesize_dialogue",
            "f5_tts_adapter_required",
            {CAPABILITY_TTS},
            family="f5_tts",
            reason="adapter_required: F5-TTS has no pinned executable Comfy API template",
            provenance=("https://github.com/SWivid/F5-TTS",),
        ),
        _disabled(
            "apply_lipsync",
            "musetalk_unvalidated",
            {CAPABILITY_LIPSYNC},
            family="musetalk",
            reason="MuseTalk nodes are not in custom_nodes; Sonic is not a substitute",
            provenance=("https://github.com/kijai/ComfyUI-MuseTalk-KJ",),
        ),
        _disabled(
            "repair_video",
            "propainter_unvalidated",
            {CAPABILITY_INPAINT},
            family="propainter",
            reason="ComfyUI_ProPainter_Nodes may be installed; blocked pending local VRAM profile",
            provenance=("https://github.com/sczhou/ProPainter",),
        ),
        _disabled(
            "upscale_still",
            "tiled_diffusion_unvalidated",
            {CAPABILITY_STILL},
            family="tiled_diffusion",
            reason="ComfyUI-TiledDiffusion pack not found; ultimatesdupscale is a different node",
            provenance=("https://github.com/shiimizu/ComfyUI-TiledDiffusion",),
        ),
        _disabled(
            "upscale_still",
            "wan21_tile_video_unvalidated",
            {CAPABILITY_STILL, CAPABILITY_VIDEO_CONTEXT},
            family="wan_tile_video",
            reason="Wan 2.1 1.3B tile-control video upscale; C016-proven graph not yet router-registered",
            provenance=("https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged",),
            extra_limits={"steps": [4], "denoise": 0.35},
        ),
    ]
    return rows


def write_seed_catalog(layout: GvdLayout, graph_bytes: bytes | None = None) -> None:
    layout.ensure()
    impls = seed_implementations(graph_bytes)
    catalog = {
        "schema_version": SCHEMA_VERSION,
        "tools": {
            name: {"status": "registered", "active_implementation": None}
            for name in PUBLIC_TOOL_NAMES
        },
        "implementations": [to_plain(impl) for impl in impls],
        "note": "Every candidate begins disabled pending local validation.",
    }
    for extra in (
        "generate_still", "upscale_still", "synthesize_dialogue",
        "apply_lipsync", "repair_video",
    ):
        catalog["tools"][extra] = {
            "status": "registered",
            "active_implementation": None,
        }
    layout.catalog_json.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    if not layout.active_json.exists():
        empty = {
            "schema_version": SCHEMA_VERSION,
            "digest": sha256_json([]),
            "implementations": [],
            "note": "no executable implementations until promotion",
        }
        layout.active_json.write_text(json.dumps(empty, indent=2), encoding="utf-8")
    payload = graph_bytes or KNOWN_GOOD_GRAPH.read_bytes()
    graph = json.loads(payload.decode("utf-8"))
    dest = layout.workflow_dir(sha256_json(graph))
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "workflow.api.json").write_text(
        json.dumps(graph, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
