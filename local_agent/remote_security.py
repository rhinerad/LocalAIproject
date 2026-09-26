#!/usr/bin/env python3
"""Identity pairing, remote-tool permissions and append-only audit records.

This module is transport-neutral.  LXMF supplies a verified source destination
hash, but neither the model nor a message field can grant itself capabilities.
The fixed tool whitelist in tools.py remains the outer boundary; this is the
additional per-identity boundary for non-desktop callers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from atomic_io import atomic_write_text

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime" / "lxmf"
PAIRINGS = RUNTIME / "paired_identities.json"
AUDIT = RUNTIME / "remote_tool_audit.jsonl"
PAIRING_AUDIT = RUNTIME / "pairing_audit.jsonl"
UNPAIRED_AUDIT = RUNTIME / "unpaired_attempts.jsonl"

# A phone can chat and use the read/sensory tools in REMOTE_DEFAULT_TOOLS.
# Everything else is denied until that exact source hash is granted the tool.
# A tool in neither set is denied. New tools stay denied until they are classified.
REMOTE_DEFAULT_TOOLS = frozenset({
    "agentic_search_docs",
    "analyze_video",
    "audio_measure",
    "await_story_image_job",
    "batch_plan",
    "cancel_phone_schedule",
    "capabilities",
    "clip_info",
    "comfy_job_status",
    "compare_voice",
    "deep_research",
    "dispatch_subtasks",
    "duration_ladder",
    "extract_video_actions",
    "fetch_url",
    "gvd_family_status",
    "gvd_inventory",
    "gvd_plan_shot",
    "gvd_qa_accepted_still",
    "gvd_qa_activation",
    "gvd_qa_attach_wd14",
    "gvd_qa_evaluate",
    "gvd_qa_loop",
    "gvd_quality_gate",
    "gvd_route_shot",
    "inspect_binary",
    "inspect_workspace",
    "list_changelog",
    "list_dir",
    "list_memory",
    "list_phone_schedules",
    "media_job_status",
    "plan_story_image",
    "plan_video_from_reference",
    "project_state",
    "prompt_pack_status",
    "propose_file_diff",
    "read_artifact",
    "read_doc",
    "read_file",
    "read_prompt",
    "read_video_metadata",
    "schedule_phone_messages",
    "search_docs",
    "see_image",
    "story_image_job_status",
    "story_stills_review_status",
    "storyboard_frame_plan",
    "transcribe",
    "validate_powerinfer_calibration",
    "validate_prompt",
    "video_frames",
    "web_search",
})
GATED_REMOTE_TOOLS = frozenset({
    "write_file",
    "apply_hex_patch",
    "run_code",
    "run_build",
    "propose_gpu",
    "batch_render",
    "start_batch_render",
    "prepare_chat_render",
    "start_current_chat_render",
    "render_story_image",
    "render_story_image_batch",
    "render_video_from_reference",
    "video_reference_job_status",
    "stop_all_comfyui",
    "comfy_generate",
    "comfy_workflow",
    "comfy_assets",
    "comfy_models",
    "comfy_nodes",
    "comfy_system",
    "comfy_process",
    "remember_fact",
    "forget_fact",
    "prepare_storyboard_review",
    "record_storyboard_reference_sheets",
    "approve_storyboard_references",
    "present_story_stills_for_review",
    "approve_story_stills",
    "ensure_sonic_pi",
    "queue_sonic_pi",
    "play_sonic_pi_note",
    "stop_sonic_pi",
    "apply_lipsync",
    "assemble_scene",
    "discover_workflows",
    "execute_continuous_take",
    "execute_fast_action",
    "execute_montage_morph",
    "execute_narrative_scene",
    "export_prompt_pack_outputs",
    "generate_still",
    "ingest_prompt_pack",
    "plan_shot_reasoning",
    "repair_jsonl_format",
    "repair_video",
    "run_prompt_pack_production",
    "run_safe_check",
    "synthesize_dialogue",
    "upscale_still",
    "write_candidate_tool",
})
IDENTITY_RE = re.compile(r"^[0-9a-f]{32}$")
_audit_lock = threading.Lock()
_pairing_lock = threading.Lock()


def normalise_identity(value: str | bytes) -> str:
    if isinstance(value, bytes):
        value = value.hex()
    text = str(value or "").strip().lower().replace(":", "")
    if not IDENTITY_RE.fullmatch(text):
        raise ValueError("LXMF source identity must be exactly 32 hexadecimal characters")
    return text


@dataclass(frozen=True)
class ToolContext:
    """Trusted request context passed below the model to tool dispatch."""

    source: str = "desktop"
    remote_identity: str = ""
    conversation_id: str = ""
    request_id: str = ""
    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    audit_path: str = ""

    @property
    def remote(self) -> bool:
        return self.source != "desktop"

    def permits(self, tool_name: str) -> bool:
        if not self.remote:
            return True
        if tool_name in REMOTE_DEFAULT_TOOLS:
            return True
        return tool_name in GATED_REMOTE_TOOLS and tool_name in self.allowed_tools


DESKTOP_CONTEXT = ToolContext()


def _empty_pairings() -> dict:
    return {"version": 1, "identities": {}}


def load_pairings(path: Path = PAIRINGS) -> dict:
    if not path.is_file():
        return _empty_pairings()
    try:
        data = json.loads(path.read_text(encoding="utf8"))
    except Exception:
        return _empty_pairings()
    if not isinstance(data, dict) or not isinstance(data.get("identities"), dict):
        return _empty_pairings()
    return data


def _save_pairings(data: dict, path: Path = PAIRINGS) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with _audit_lock:
        with path.open("a", encoding="utf8", newline="") as fh:
            fh.write(line)
            fh.flush()


def pair(identity: str, name: str = "phone", model: str = "",
         path: Path = PAIRINGS) -> dict:
    identity = normalise_identity(identity)
    now = time.time()
    with _pairing_lock:
        data = load_pairings(path)
        old = data["identities"].get(identity, {})
        record = {
            "name": (name or old.get("name") or "phone")[:80],
            "active": True,
            "allowed_tools": sorted(set(old.get("allowed_tools") or [])),
            "conversation_id": old.get("conversation_id", ""),
            "model": model or old.get("model", ""),
            "added_at": old.get("added_at", now),
            "updated_at": now,
        }
        data["identities"][identity] = record
        _save_pairings(data, path)
    _append_jsonl(path.parent / PAIRING_AUDIT.name,
                  {"at": now, "event": "pair", "identity": identity,
                   "name": record["name"]})
    return record


def revoke(identity: str, path: Path = PAIRINGS) -> bool:
    identity = normalise_identity(identity)
    with _pairing_lock:
        data = load_pairings(path)
        record = data["identities"].get(identity)
        if not record:
            return False
        record["active"] = False
        record["updated_at"] = time.time()
        _save_pairings(data, path)
    _append_jsonl(path.parent / PAIRING_AUDIT.name,
                  {"at": time.time(), "event": "revoke", "identity": identity})
    return True


def set_tool_grant(identity: str, tool_name: str, allowed: bool,
                   path: Path = PAIRINGS) -> dict:
    identity = normalise_identity(identity)
    if tool_name not in GATED_REMOTE_TOOLS:
        raise ValueError(f"{tool_name!r} is not a remote-gated tool")
    with _pairing_lock:
        data = load_pairings(path)
        record = data["identities"].get(identity)
        if not record:
            raise ValueError("identity is not paired")
        grants = set(record.get("allowed_tools") or [])
        (grants.add if allowed else grants.discard)(tool_name)
        record["allowed_tools"] = sorted(grants)
        record["updated_at"] = time.time()
        _save_pairings(data, path)
    _append_jsonl(path.parent / PAIRING_AUDIT.name,
                  {"at": time.time(), "event": "grant" if allowed else "deny",
                   "identity": identity, "tool": tool_name})
    return record


def get_pair(identity: str | bytes, path: Path = PAIRINGS) -> dict | None:
    try:
        key = normalise_identity(identity)
    except ValueError:
        return None
    record = load_pairings(path)["identities"].get(key)
    return record if record and record.get("active") else None


def record_unpaired_attempt(identity: str | bytes, request_id: str = "",
                            path: Path = UNPAIRED_AUDIT) -> None:
    """Audit a refused pairing attempt without storing its message content.

    An operator must explicitly pair the recorded LXMF *delivery* address;
    receiving a message never grants a remote identity access by itself.
    """
    try:
        key = normalise_identity(identity)
    except ValueError:
        return
    _append_jsonl(path, {
        "at": time.time(),
        "event": "unpaired_attempt",
        "identity": key,
        "request_id": str(request_id or "")[:128],
    })


def set_conversation(identity: str | bytes, cid: str,
                     path: Path = PAIRINGS) -> None:
    key = normalise_identity(identity)
    with _pairing_lock:
        data = load_pairings(path)
        record = data["identities"].get(key)
        if not record or not record.get("active"):
            raise ValueError("identity is not paired")
        record["conversation_id"] = cid
        record["updated_at"] = time.time()
        _save_pairings(data, path)


def context_for(identity: str | bytes, conversation_id: str = "",
                request_id: str = "", path: Path = PAIRINGS,
                audit_path: Path | None = None) -> ToolContext | None:
    try:
        key = normalise_identity(identity)
    except ValueError:
        return None
    record = get_pair(key, path)
    if not record:
        return None
    return ToolContext(source="phone", remote_identity=key,
                       conversation_id=conversation_id, request_id=request_id,
                       allowed_tools=frozenset(record.get("allowed_tools") or []),
                       audit_path=str(audit_path or ""))


def _redact_args(args: dict) -> dict:
    """Keep audit records useful without copying file bodies or credentials."""
    raw = json.dumps(args or {}, sort_keys=True, ensure_ascii=False, default=str)
    summary: dict = {
        "keys": sorted(str(k) for k in (args or {})),
        "sha256": hashlib.sha256(raw.encode("utf8")).hexdigest(),
        "json_bytes": len(raw.encode("utf8")),
    }
    for key in ("path", "clip", "action", "name"):
        value = (args or {}).get(key)
        if isinstance(value, (str, int, float, bool)):
            summary[key] = str(value)[:260]
    return summary


def audit_tool(context: ToolContext, name: str, args: dict, outcome: str,
               detail: str = "", path: Path | None = None) -> None:
    if not context.remote:
        return
    destination = path or (Path(context.audit_path) if context.audit_path else AUDIT)
    _append_jsonl(destination, {
        "at": time.time(),
        "source": context.source,
        "identity": context.remote_identity,
        "conversation_id": context.conversation_id,
        "request_id": context.request_id,
        "tool": name,
        "outcome": outcome,
        "detail": detail[:500],
        "args": _redact_args(args or {}),
    })


def _cli() -> int:
    parser = argparse.ArgumentParser(description="Pair and permission Sideband identities")
    subs = parser.add_subparsers(dest="command", required=True)
    add = subs.add_parser("add", help="pair or reactivate an identity (read/chat by default)")
    add.add_argument("identity")
    add.add_argument("--name", default="phone")
    add.add_argument("--model", default="")
    subs.add_parser("list", help="list paired identities")
    rev = subs.add_parser("revoke", help="disable an identity without erasing its record")
    rev.add_argument("identity")
    for command in ("grant", "deny"):
        p = subs.add_parser(command, help=f"{command} one gated tool")
        p.add_argument("identity")
        p.add_argument("tool", choices=sorted(GATED_REMOTE_TOOLS))
    args = parser.parse_args()
    if args.command == "add":
        print(json.dumps(pair(args.identity, args.name, args.model), indent=2))
    elif args.command == "list":
        print(json.dumps(load_pairings(), indent=2))
    elif args.command == "revoke":
        print(json.dumps({"revoked": revoke(args.identity)}))
    else:
        print(json.dumps(set_tool_grant(args.identity, args.tool,
                                        args.command == "grant"), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
