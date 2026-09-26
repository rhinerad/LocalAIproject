#!/usr/bin/env python3
"""Canonical asset registry + continuity binding helpers (audit §5).

Offline-safe. No ComfyUI / GPU / network. Stores versioned character /
location / voice / boundary-frame records with content hashes and roles.

Continuity path (selected parent → boundary PNG → Comfy LoadImage →
MiniMaxH3ImageToVideo.first_frame) reuses the same bind contract as
``bind_h3_image_frames`` / ``pipeline_reference.bind_base_h3``.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

# --- roles -----------------------------------------------------------------

class AssetRole(str, Enum):
    IDENTITY = "identity"
    WARDROBE = "wardrobe"
    LOCATION = "location"
    REFERENCE = "reference"
    BOUNDARY_FRAME = "boundary_frame"
    VOICE = "voice"


ASSET_ROLES = frozenset(r.value for r in AssetRole)

# --- edit relationship strategy (audit §5) ---------------------------------

class EditRelationship(str, Enum):
    CONTINUOUS = "continuous"
    NEW_ANGLE = "new_angle"
    NEW_SCENE = "new_scene"
    CHARACTER_RETURN = "character_return"
    BRIDGE = "bridge"


# Maps edit relationship → continuity strategy notes / required anchors.
EDIT_RELATIONSHIP_STRATEGY: dict[str, dict[str, Any]] = {
    EditRelationship.CONTINUOUS.value: {
        "bind_parent_boundary": True,
        "reanchor_canonical": False,
        "require_parent_selected": True,
        "description": "Match cut: child first_frame = parent clean-render boundary PNG.",
    },
    EditRelationship.NEW_ANGLE.value: {
        "bind_parent_boundary": False,
        "reanchor_canonical": True,
        "require_parent_selected": False,
        "description": "Same scene, new camera; re-anchor from canonical identity/location.",
    },
    EditRelationship.NEW_SCENE.value: {
        "bind_parent_boundary": False,
        "reanchor_canonical": True,
        "require_parent_selected": False,
        "description": "Hard cut to new location; use location + identity canonical assets.",
    },
    EditRelationship.CHARACTER_RETURN.value: {
        "bind_parent_boundary": False,
        "reanchor_canonical": True,
        "require_parent_selected": False,
        "description": "Character re-enters; prefer identity/wardrobe canonical assets.",
    },
    EditRelationship.BRIDGE.value: {
        "bind_parent_boundary": True,
        "reanchor_canonical": True,
        "require_parent_selected": True,
        "description": "Bridge shot: parent boundary plus canonical re-anchor at planned cut.",
    },
}

# Continuity modes aligned with shot.schema / dataset_synthesizer.
CONTINUITY_MODES = frozenset({"cut", "continuous", "reference", "bridge"})


class ContinuityError(ValueError):
    """Raised when continuity rules reject a parent / binding."""


# --- records ---------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_record(payload: Mapping[str, Any]) -> str:
    return _sha256_bytes(
        json.dumps(payload, sort_keys=True, ensure_ascii=False,
                   separators=(",", ":"), allow_nan=False).encode()
    )


@dataclass
class CanonicalAsset:
    """Versioned asset record (character / location / voice / boundary)."""
    asset_id: str
    role: str
    version: str
    path: str
    content_hash: str
    label: str = ""
    speaker_id: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.role not in ASSET_ROLES:
            raise ContinuityError(
                f"unknown asset role {self.role!r}; expected one of {sorted(ASSET_ROLES)}"
            )
        if not self.asset_id or not self.version or not self.content_hash:
            raise ContinuityError("asset_id, version, and content_hash are required")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "CanonicalAsset":
        return cls(
            asset_id=str(obj["asset_id"]),
            role=str(obj["role"]),
            version=str(obj["version"]),
            path=str(obj["path"]),
            content_hash=str(obj["content_hash"]),
            label=str(obj.get("label") or ""),
            speaker_id=(str(obj["speaker_id"]) if obj.get("speaker_id") else None),
            meta=dict(obj.get("meta") or {}),
        )


@dataclass
class BoundaryRecord:
    """Boundary frame extracted from a CLEAN render (before VHS/subtitles)."""
    attempt_id: str
    shot_id: str
    frame_index: int
    png_path: str
    content_hash: str
    source_artifact: str
    extracted_before_vhs: bool = True
    extracted_before_subtitles: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "BoundaryRecord":
        return cls(
            attempt_id=str(obj["attempt_id"]),
            shot_id=str(obj["shot_id"]),
            frame_index=int(obj["frame_index"]),
            png_path=str(obj["png_path"]),
            content_hash=str(obj["content_hash"]),
            source_artifact=str(obj["source_artifact"]),
            extracted_before_vhs=bool(obj.get("extracted_before_vhs", True)),
            extracted_before_subtitles=bool(obj.get("extracted_before_subtitles", True)),
        )


@dataclass
class ContinuityBindPlan:
    """Resolved path from parent SELECTED attempt → H3 first_frame bind."""
    parent_attempt_id: str
    frame_index: int
    lossless_png_path: str
    comfy_upload_name: str
    load_image_node_id: str = "1001"
    h3_field: str = "first_frame"
    content_hash: str | None = None
    edit_relationship: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AssetRegistry:
    """In-memory / JSON-backed registry of versioned canonical assets."""

    def __init__(self) -> None:
        self._assets: dict[str, CanonicalAsset] = {}
        self._boundaries: dict[str, BoundaryRecord] = {}  # attempt_id → boundary

    def upsert(self, asset: CanonicalAsset) -> CanonicalAsset:
        key = f"{asset.asset_id}@{asset.version}"
        self._assets[key] = asset
        return asset

    def get(self, asset_id: str, version: str | None = None) -> CanonicalAsset | None:
        if version is not None:
            return self._assets.get(f"{asset_id}@{version}")
        # latest by version string sort (semver-ish / lexical)
        matches = [a for k, a in self._assets.items() if a.asset_id == asset_id]
        if not matches:
            return None
        return sorted(matches, key=lambda a: a.version)[-1]

    def list_by_role(self, role: str) -> list[CanonicalAsset]:
        return [a for a in self._assets.values() if a.role == role]

    def record_boundary(self, boundary: BoundaryRecord) -> BoundaryRecord:
        if not boundary.extracted_before_vhs or not boundary.extracted_before_subtitles:
            raise ContinuityError(
                "boundary must be extracted from clean render before VHS/subtitles"
            )
        if boundary.frame_index < 0:
            raise ContinuityError("boundary frame_index must be >= 0")
        if not re.fullmatch(r"[0-9a-f]{64}", boundary.content_hash):
            raise ContinuityError("boundary content_hash must be sha256 hex")
        self._boundaries[boundary.attempt_id] = boundary
        # Also register as a boundary_frame asset
        self.upsert(
            CanonicalAsset(
                asset_id=f"boundary:{boundary.attempt_id}",
                role=AssetRole.BOUNDARY_FRAME.value,
                version="1",
                path=boundary.png_path,
                content_hash=boundary.content_hash,
                label=f"{boundary.shot_id}@{boundary.frame_index}",
                meta={"attempt_id": boundary.attempt_id, "frame_index": boundary.frame_index},
            )
        )
        return boundary

    def get_boundary(self, attempt_id: str) -> BoundaryRecord | None:
        return self._boundaries.get(attempt_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assets": [a.to_dict() for a in self._assets.values()],
            "boundaries": [b.to_dict() for b in self._boundaries.values()],
        }

    @classmethod
    def from_dict(cls, obj: Mapping[str, Any]) -> "AssetRegistry":
        reg = cls()
        for raw in obj.get("assets") or []:
            reg.upsert(CanonicalAsset.from_dict(raw))
        for raw in obj.get("boundaries") or []:
            # bypass double-upsert side effects carefully
            b = BoundaryRecord.from_dict(raw)
            reg._boundaries[b.attempt_id] = b
        return reg

    def save_json(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8")

    @classmethod
    def load_json(cls, path: Path | str) -> "AssetRegistry":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)


# --- continuity rules (APIs) -----------------------------------------------

def assert_parent_usable(
    *,
    parent_state: str | None,
    parent_attempt_id: str | None,
    boundary: BoundaryRecord | None,
    reject_broken: bool = True,
) -> None:
    """Reject broken / non-SELECTED parents before binding a child."""
    if not parent_attempt_id:
        raise ContinuityError("parent_attempt_id required for continuous/bridge bind")
    state = str(parent_state or "").upper()
    if state != "SELECTED":
        raise ContinuityError(
            f"parent attempt {parent_attempt_id} state={state!r} is not SELECTED"
        )
    if reject_broken and boundary is None:
        raise ContinuityError(
            f"parent {parent_attempt_id} has no recorded clean-render boundary"
        )
    if boundary is not None:
        if not boundary.extracted_before_vhs or not boundary.extracted_before_subtitles:
            raise ContinuityError("parent boundary was not taken from clean render")


def record_boundary_from_png(
    registry: AssetRegistry,
    *,
    attempt_id: str,
    shot_id: str,
    frame_index: int,
    png_path: Path | str,
    source_artifact: str,
    extracted_before_vhs: bool = True,
    extracted_before_subtitles: bool = True,
) -> BoundaryRecord:
    """Hash + record a lossless PNG boundary; fail if finishing flags are wrong."""
    if not extracted_before_vhs or not extracted_before_subtitles:
        raise ContinuityError(
            "extract boundary from clean render BEFORE VHS/subtitles finishing"
        )
    path = Path(png_path)
    if path.suffix.lower() != ".png":
        raise ContinuityError(f"boundary must be lossless PNG, got {path.suffix!r}")
    if not path.is_file():
        raise ContinuityError(f"boundary PNG missing: {path}")
    digest = sha256_file(path)
    return registry.record_boundary(
        BoundaryRecord(
            attempt_id=attempt_id,
            shot_id=shot_id,
            frame_index=int(frame_index),
            png_path=str(path),
            content_hash=digest,
            source_artifact=source_artifact,
            extracted_before_vhs=True,
            extracted_before_subtitles=True,
        )
    )


def comfy_input_relative_name(png_path: Path | str, *, prefix: str = "") -> str:
    """Safe Comfy input-relative upload name (no abs / .. / drive / backslash)."""
    p = Path(png_path)
    name = p.name
    if prefix:
        name = f"{prefix.rstrip('_')}_{name}"
    if not name or ".." in name or "/" in name or "\\" in name or ":" in name:
        raise ContinuityError(f"unsafe Comfy upload name derived from {png_path!r}")
    if not name.lower().endswith(".png"):
        raise ContinuityError("Comfy continuity upload must be a .png name")
    return name


def build_continuity_bind_plan(
    registry: AssetRegistry,
    *,
    parent_attempt_id: str,
    parent_state: str = "SELECTED",
    edit_relationship: str = EditRelationship.CONTINUOUS.value,
    upload_prefix: str = "",
) -> ContinuityBindPlan:
    """selected parent → frame index → PNG → upload name → LoadImage/first_frame plan."""
    strategy = EDIT_RELATIONSHIP_STRATEGY.get(edit_relationship)
    if strategy is None:
        raise ContinuityError(
            f"unknown edit_relationship {edit_relationship!r}; "
            f"expected one of {sorted(EDIT_RELATIONSHIP_STRATEGY)}"
        )
    boundary = registry.get_boundary(parent_attempt_id)
    if strategy["require_parent_selected"] or strategy["bind_parent_boundary"]:
        assert_parent_usable(
            parent_state=parent_state,
            parent_attempt_id=parent_attempt_id,
            boundary=boundary if strategy["bind_parent_boundary"] else boundary,
            reject_broken=bool(strategy["bind_parent_boundary"]),
        )
    if not strategy["bind_parent_boundary"]:
        # re-anchor path: no parent PNG required; caller supplies canonical assets
        raise ContinuityError(
            f"edit_relationship={edit_relationship} does not bind parent boundary; "
            "use reanchor_from_canonical_assets() instead"
        )
    assert boundary is not None
    upload = comfy_input_relative_name(boundary.png_path, prefix=upload_prefix)
    return ContinuityBindPlan(
        parent_attempt_id=parent_attempt_id,
        frame_index=boundary.frame_index,
        lossless_png_path=boundary.png_path,
        comfy_upload_name=upload,
        content_hash=boundary.content_hash,
        edit_relationship=edit_relationship,
    )


def reanchor_from_canonical_assets(
    registry: AssetRegistry,
    asset_ids: Iterable[str],
    *,
    roles: Iterable[str] | None = None,
) -> list[CanonicalAsset]:
    """At planned cuts, re-anchor from registry assets (identity/wardrobe/location)."""
    wanted_roles = set(roles) if roles is not None else {
        AssetRole.IDENTITY.value,
        AssetRole.WARDROBE.value,
        AssetRole.LOCATION.value,
        AssetRole.REFERENCE.value,
    }
    out: list[CanonicalAsset] = []
    for aid in asset_ids:
        asset = registry.get(aid)
        if asset is None:
            raise ContinuityError(f"canonical asset not found: {aid}")
        if asset.role not in wanted_roles:
            continue
        out.append(asset)
    if not out:
        raise ContinuityError("re-anchor requires at least one matching canonical asset")
    return out


def apply_bind_plan_to_graph(
    graph: dict,
    plan: ContinuityBindPlan,
    *,
    bind_fn: Any | None = None,
) -> dict:
    """Apply ContinuityBindPlan via bind_h3_image_frames (or compatible callable).

    ``bind_fn(graph, first_frame_path=..., last_frame_path=...)`` must match the
    orchestrator / pipeline_reference contract. If omitted, performs the same
    LoadImage → MiniMaxH3ImageToVideo.first_frame wiring inline.
    """
    if bind_fn is not None:
        return bind_fn(graph, first_frame_path=plan.comfy_upload_name, last_frame_path=None)

    g = graph
    target_id = None
    if isinstance(g.get("20"), dict) and str(g["20"].get("class_type") or "") == "MiniMaxH3ImageToVideo":
        target_id = "20"
    else:
        for nid, node in g.items():
            if isinstance(node, dict) and str(node.get("class_type") or "") == "MiniMaxH3ImageToVideo":
                target_id = str(nid)
                break
    if target_id is None:
        raise ContinuityError("graph has no MiniMaxH3ImageToVideo node to bind")
    nid = plan.load_image_node_id
    g[nid] = {"class_type": "LoadImage", "inputs": {"image": plan.comfy_upload_name}}
    node = g[target_id]
    inputs = dict(node.get("inputs") or {})
    inputs[plan.h3_field] = [nid, 0]
    g[target_id] = {**node, "inputs": inputs}
    meta = g.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["continuity_bind"] = plan.to_dict()
    return g


def edit_strategy(relationship: str) -> dict[str, Any]:
    """Lookup helper for the edit-relationship strategy table."""
    key = str(relationship or "").strip().lower()
    if key not in EDIT_RELATIONSHIP_STRATEGY:
        raise ContinuityError(
            f"unknown edit relationship {relationship!r}; "
            f"expected one of {sorted(EDIT_RELATIONSHIP_STRATEGY)}"
        )
    return dict(EDIT_RELATIONSHIP_STRATEGY[key])


def parent_switch_invalidates_child(
    *,
    bound_parent_attempt_id: str | None,
    current_selected_parent_attempt_id: str | None,
) -> bool:
    """True when intentional parent SELECTED switch invalidates a child bind."""
    if not bound_parent_attempt_id:
        return False
    if not current_selected_parent_attempt_id:
        return True
    return bound_parent_attempt_id != current_selected_parent_attempt_id
