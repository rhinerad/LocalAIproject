"""Deterministic scene-to-tool routing. The planner cannot invent node types."""
from __future__ import annotations

import re
from typing import Any, Iterable

from .schema import (
    CAPABILITY_CONTINUATION,
    CAPABILITY_FAST,
    CAPABILITY_IDENTITY,
    CAPABILITY_MONTAGE,
    CAPABILITY_NARRATIVE,
    CAPABILITY_STILL,
    CAPABILITY_TTS,
    CAPABILITY_LIPSYNC,
    CAPABILITY_INPAINT,
    CAPABILITY_MOTION_REFERENCE,
    RouteDecision,
    ShotManifest,
    ToolImplementation,
    ToolName,
    can_activate,
    sha256_json,
    to_plain,
)
from .switch import APPROVAL_HEADROOM_MIB

SCORE_WEIGHTS = {
    "identity": 0.35,
    "motion": 0.30,
    "style": 0.15,
    "audio": 0.10,
    "reliability": 0.10,
}
LATENCY_PENALTY = 0.10
SWITCH_PENALTY = 0.08

# Operator engine policy (2026-09-26b). MiniMax is the default video engine.
# Candidates are ranked by engine tier first and quality score second, so a
# Wan row can win only when (a) manifest.requested_engine == "wan" or (b) no
# MiniMax row and no other-family row fit the shot. Case (b) is never
# silent: the decision carries ENGINE_FALLBACK_WAN and an operator_notice.
ENGINE_MINIMAX = "minimax"
ENGINE_WAN = "wan"
ENGINE_OTHER = "other"
KNOWN_ENGINES = frozenset({ENGINE_MINIMAX, ENGINE_WAN})
ENGINE_TIER_DEFAULT = {ENGINE_MINIMAX: 0, ENGINE_OTHER: 1, ENGINE_WAN: 2}
_WAN_TOKEN = re.compile(r"(?:^|[^a-z])wan(?![a-z])")
_H3_TOKEN = re.compile(r"(?:^|[^a-z0-9])(?:fast)?h3(?![a-z0-9])")

PREFERRED_TOOL: dict[str, ToolName] = {
    "continuous": "execute_continuous_take",
    "identity": "execute_narrative_scene",
    "morph": "execute_montage_morph",
    "independent": "execute_fast_action",
}


class RoutingError(ValueError):
    pass


def engine_family(impl: ToolImplementation) -> str:
    """Which engine a catalog row belongs to: "minimax", "wan" or "other".

    ``limits["engine_family"]`` wins when a row states it. Otherwise the
    implementation_id and every stage model_family_key are matched: MiniMax
    H3 and its FastH3 distillations are one family; anything Wan-based (I2V,
    dual MoE, 8-step, Animate, VACE, tile-video) is the other. Everything
    else (LTX, AnimateDiff, IP-Adapter, SDXL, ...) is neutral.
    """
    stated = str(impl.limits.get("engine_family") or "").strip().lower()
    if stated in KNOWN_ENGINES or stated == ENGINE_OTHER:
        return stated
    parts = [impl.implementation_id] + [s.template.model_family_key for s in impl.stages]
    text = " ".join(str(p) for p in parts).lower()
    if "minimax" in text or _H3_TOKEN.search(text):
        return ENGINE_MINIMAX
    if _WAN_TOKEN.search(text):
        return ENGINE_WAN
    return ENGINE_OTHER


def engine_tier(impl: ToolImplementation, requested_engine: str | None) -> int:
    """Lower sorts first. Default: MiniMax 0, other 1, Wan 2. An explicit Wan
    request puts Wan at 0 and everything else at 1 (score decides among them)."""
    family = engine_family(impl)
    if requested_engine == ENGINE_WAN:
        return 0 if family == ENGINE_WAN else 1
    return ENGINE_TIER_DEFAULT[family]


def preferred_tool(manifest: ShotManifest) -> ToolName:
    if manifest.continuity_mode == "continuous":
        return "execute_continuous_take"
    if manifest.continuity_mode == "morph" or manifest.prompt_keyframes:
        return "execute_montage_morph"
    if manifest.continuity_mode == "identity" or manifest.character_state:
        return "execute_narrative_scene"
    return "execute_fast_action"


def required_capabilities(manifest: ShotManifest) -> frozenset[str]:
    required = set(manifest.hard_requirements)
    mode = manifest.continuity_mode
    if mode == "continuous":
        required.add(CAPABILITY_CONTINUATION)
    elif mode == "morph":
        required.add(CAPABILITY_MONTAGE)
    elif mode == "identity":
        required.add(CAPABILITY_NARRATIVE)
        required.add(CAPABILITY_IDENTITY)
    elif mode == "independent":
        required.add(CAPABILITY_FAST)
    if manifest.character_state and mode == "continuous":
        required.add(CAPABILITY_IDENTITY)
        required.add(CAPABILITY_CONTINUATION)
    if manifest.start_frame:
        required.add("first_frame")
    if manifest.end_frame:
        required.add("last_frame")
    if manifest.context_video:
        required.add("video_context")
    if manifest.audio:
        required.add("audio_conditioning")
    if manifest.motion_reference_video:
        # Motion transfer from a reference clip is its own capability: the
        # clip drives pose and timing, it is not continuation context. A
        # named character riding that motion still needs identity conditioning.
        required.add(CAPABILITY_MOTION_REFERENCE)
        if manifest.character_state:
            required.add(CAPABILITY_IDENTITY)
    if "dialogue_visible_mouth" in manifest.hard_requirements:
        required.update({CAPABILITY_TTS, CAPABILITY_LIPSYNC})
    if "local_repair" in manifest.hard_requirements:
        required.add(CAPABILITY_INPAINT)
    return frozenset(required)


def validate_manifest(manifest: ShotManifest) -> list[str]:
    reasons: list[str] = []
    if not manifest.shot_id.strip():
        reasons.append("missing_shot_id")
    if manifest.duration_s <= 0:
        reasons.append("non_positive_duration")
    if manifest.width < 1 or manifest.height < 1:
        reasons.append("invalid_dimensions")
    if manifest.fps_den < 1 or manifest.fps_num < 1:
        reasons.append("invalid_timebase")
    if manifest.continuity_mode == "continuous" and not (
        manifest.start_frame or manifest.context_video
    ):
        reasons.append("continuous_requires_start_or_context")
    if manifest.continuity_mode == "morph" and not manifest.prompt_keyframes:
        reasons.append("morph_requires_prompt_schedule")
    if manifest.continuity_mode == "identity" and not manifest.character_state:
        reasons.append("identity_requires_character_state")
    for key, conf in manifest.inferred_confidence.items():
        if conf < 0.5 and key in manifest.hard_requirements:
            reasons.append("needs_manifest_review")
    if manifest.requested_engine and manifest.requested_engine not in KNOWN_ENGINES:
        reasons.append("unknown_requested_engine:" + manifest.requested_engine)
    return reasons


def _select_profile(
    impl: ToolImplementation,
    manifest: ShotManifest,
    inventory: dict[str, Any],
    operator_approval: bool = False,
) -> tuple[str | None, list[str]]:
    reasons: list[str] = []
    free = (inventory.get("gpu") or {}).get("memory_free_mib")
    headroom = int(inventory.get("headroom_mib") or 2048)
    if operator_approval and impl.limits.get("requires_operator_approval"):
        headroom = APPROVAL_HEADROOM_MIB
    local = [p for p in impl.profiles if p.evidence == "local"]
    if not local:
        return None, ["PROFILE_REQUIRED"]
    matching = []
    for profile in local:
        if profile.peak_gpu_mib is None:
            reasons.append("unknown_vram")
            continue
        if free is not None and profile.peak_gpu_mib + headroom > int(free):
            reasons.append("RESOURCE_BLOCKED")
            continue
        matching.append(profile)
    if not matching:
        return None, reasons or ["PROFILE_REQUIRED"]
    return matching[0].profile_id, []


def _quality_floor_ok(impl: ToolImplementation, manifest: ShotManifest) -> bool:
    for axis, floor in (manifest.priorities or {}).items():
        if floor <= 0:
            continue
        measured = impl.quality_scores.get(axis)
        if measured is None:
            return False
        if measured < floor:
            return False
    return True


def _score(impl: ToolImplementation, manifest: ShotManifest) -> float | None:
    weights = dict(SCORE_WEIGHTS)
    pri = manifest.priorities or {}
    if pri:
        total = sum(max(0.0, float(v)) for v in pri.values()) or 1.0
        for axis in ("identity", "motion", "style", "audio"):
            if axis in pri:
                weights[axis] = 0.90 * (float(pri[axis]) / total)
    score = 0.0
    for axis, weight in weights.items():
        key = {"identity": "identity", "motion": "motion", "style": "style",
               "audio": "audio", "reliability": "reliability"}[axis]
        measured = impl.quality_scores.get(key)
        if measured is None:
            if axis in manifest.hard_requirements or axis in (manifest.priorities or {}):
                return None
            measured = 0.0
        score += weight * float(measured)
    latency = float(impl.quality_scores.get("latency_norm") or 0.0)
    switch = float(impl.quality_scores.get("switch_cost_norm") or 0.0)
    score -= LATENCY_PENALTY * latency
    score -= SWITCH_PENALTY * switch
    return score


def _compatible(
    impl: ToolImplementation,
    required: frozenset[str],
    inventory: dict[str, Any],
    manifest: ShotManifest,
    *,
    local_only: bool,
    operator_approval: bool = False,
) -> tuple[bool, list[str], str | None]:
    reasons: list[str] = []
    if impl.status != "active":
        reasons.append("not_active")
    if impl.limits.get("requires_operator_approval") and not operator_approval:
        # Until 2026-09-26b this flag only changed the headroom arithmetic
        # once approval was already present, so on its own it gated nothing.
        # It now means what it says: no operator approval, no selection.
        reasons.append("operator_approval_required")
    if not required <= impl.capabilities:
        missing = sorted(required - impl.capabilities)
        reasons.append("missing_capabilities:" + ",".join(missing))
    # A row may insist that the shot actually needs one of its capabilities
    # (2026-09-26, motion transfer): a reference-video implementation offers
    # identity + narrative too, but must never be chosen for a shot that has
    # no motion reference, since its template renders nothing else.
    needs = [str(c) for c in (impl.limits.get("requires_capabilities") or [])]
    unmet = sorted(c for c in needs if c not in required)
    if unmet:
        reasons.append("shot_lacks_required_capability:" + ",".join(unmet))
    if local_only and not impl.local_only:
        reasons.append("local_only_policy")
    env = inventory.get("environment_sha256")
    if env and impl.runtime.environment_sha256 not in {env, "0" * 64}:
        if impl.runtime.environment_sha256 != env:
            reasons.append("runtime_mismatch")
    profile_id, profile_reasons = _select_profile(
        impl, manifest, inventory, operator_approval=operator_approval
    )
    reasons.extend(profile_reasons)
    if not _quality_floor_ok(impl, manifest):
        reasons.append("quality_floor")
    ok, activate_reasons = can_activate(impl)
    if not ok and impl.status == "active":
        reasons.extend(activate_reasons)
    return (not reasons), reasons, profile_id


def route(
    manifest: ShotManifest,
    implementations: Iterable[ToolImplementation],
    inventory: dict[str, Any],
    *,
    local_only: bool = True,
    registry_digest: str | None = None,
    operator_approval: bool = False,
) -> RouteDecision:
    review = validate_manifest(manifest)
    digest = registry_digest or sha256_json([to_plain(i) for i in implementations])
    if "needs_manifest_review" in review or (
        review and any(r.startswith("missing") or r.endswith("requires_character_state")
                       or "requires" in r or r.startswith("unknown_requested_engine")
                       for r in review)
    ):
        if review:
            return RouteDecision(
                status="needs_manifest_review" if "needs_manifest_review" in review
                else "blocked",
                tool_name=None,
                implementation_id=None,
                profile_id=None,
                registry_digest=digest,
                stage_ids=(),
                reason_codes=tuple(["NEEDS_MANIFEST_REVIEW"] + review)
                if "needs_manifest_review" in review
                else tuple(review),
                rejection_log=(),
            )
    required = required_capabilities(manifest)
    preferred = preferred_tool(manifest)
    by_id = {impl.implementation_id: impl for impl in implementations}
    family = [impl for impl in implementations if impl.tool_name == preferred]
    log: list[dict[str, Any]] = []
    requested = manifest.requested_engine

    def unfit(engine: str, winner_id: str) -> list[str]:
        """Every considered row of one engine family that lost, with its reasons."""
        rows: list[str] = []
        for entry in log:
            impl = by_id.get(entry["implementation_id"])
            if impl is None or impl.implementation_id == winner_id:
                continue
            if engine_family(impl) != engine:
                continue
            reasons = ",".join(entry["reasons"]) or "outscored"
            rows.append(f"{impl.implementation_id}:{reasons}")
        return rows

    def engine_policy(winner: ToolImplementation) -> tuple[list[str], str, str, str | None]:
        """(reason_codes, engine, engine_selection, operator_notice) for a winner."""
        engine = engine_family(winner)
        if engine == ENGINE_WAN and requested == ENGINE_WAN:
            return (
                ["ENGINE_EXPLICIT_WAN"], engine, "explicit_request",
                f"Wan selected ({winner.implementation_id}) because the operator's "
                "request explicitly named Wan (requested_engine=wan).",
            )
        if engine == ENGINE_WAN:
            minimax = unfit(ENGINE_MINIMAX, winner.implementation_id)
            others = unfit(ENGINE_OTHER, winner.implementation_id)
            if minimax:
                because = ("every MiniMax implementation for this shot was rejected: "
                           + "; ".join(minimax))
                codes = ["ENGINE_FALLBACK_WAN"] + [f"minimax_unfit:{row}" for row in minimax]
            else:
                because = f"no MiniMax implementation is active for {winner.tool_name}"
                codes = ["ENGINE_FALLBACK_WAN", "minimax_absent"]
            also = f" (also rejected: {'; '.join(others)})" if others else ""
            notice = (
                f"MiniMax didn't fit, used Wan instead ({winner.implementation_id}), "
                f"because {because}. Wan was the only compatible implementation left"
                f"{also}. The operator was not asked for Wan; confirm before rendering."
            )
            return codes, engine, "fallback", notice
        if requested == ENGINE_WAN:
            wan = unfit(ENGINE_WAN, winner.implementation_id)
            because = "; ".join(wan) if wan else (
                f"no Wan implementation is active for {winner.tool_name}")
            codes = ["REQUESTED_ENGINE_UNAVAILABLE:wan"] + [f"wan_unfit:{row}" for row in wan]
            notice = (
                f"The operator requested Wan but it could not be used ({because}); "
                f"selected {winner.implementation_id} ({engine}) instead."
            )
            return codes, engine, "requested_engine_unavailable", notice
        return [], engine, "default", None

    def consider(cands: list[ToolImplementation], visited: set[str]) -> RouteDecision | None:
        viable: list[tuple[int, float, ToolImplementation, str]] = []
        for impl in cands:
            if impl.implementation_id in visited:
                continue
            ok, reasons, profile_id = _compatible(
                impl, required, inventory, manifest, local_only=local_only,
                operator_approval=operator_approval,
            )
            log.append({
                "implementation_id": impl.implementation_id,
                "ok": ok,
                "reasons": reasons,
            })
            if not ok or profile_id is None:
                continue
            score = _score(impl, manifest)
            if score is None:
                log[-1]["reasons"].append("missing_quality_measurement")
                continue
            viable.append((engine_tier(impl, requested), score, impl, profile_id))
        if not viable:
            return None
        # Engine tier first (MiniMax-first policy), measured score second.
        viable.sort(key=lambda row: (row[0], -row[1], row[2].implementation_id))
        _tier, score, winner, profile_id = viable[0]
        codes, engine, selection, notice = engine_policy(winner)
        return RouteDecision(
            status="selected",
            tool_name=winner.tool_name,
            implementation_id=winner.implementation_id,
            profile_id=profile_id,
            registry_digest=digest,
            stage_ids=tuple(s.stage_id for s in winner.stages),
            reason_codes=tuple(codes),
            rejection_log=tuple(log),
            score=score,
            engine=engine,
            engine_selection=selection,
            operator_notice=notice,
        )

    visited: set[str] = set()
    chosen = consider(family, visited)
    if chosen:
        return chosen
    fallbacks: list[ToolImplementation] = []
    for impl in family:
        for fid in impl.fallback_ids:
            if fid in visited or fid not in by_id:
                continue
            visited.add(impl.implementation_id)
            fallbacks.append(by_id[fid])
    chosen = consider(fallbacks, visited)
    if chosen:
        return chosen
    codes = ["NO_COMPATIBLE_TOOL", "UNAVAILABLE_CAPABILITY"]
    if not any(impl.status == "active" and impl.tool_name == preferred for impl in implementations):
        codes.append("UNAVAILABLE_CAPABILITY")
    if required:
        codes.append("missing:" + ",".join(sorted(required)))
    return RouteDecision(
        status="blocked",
        tool_name=preferred,
        implementation_id=None,
        profile_id=None,
        registry_digest=digest,
        stage_ids=(),
        reason_codes=tuple(codes),
        rejection_log=tuple(log),
        discovery_requested=True,
    )
