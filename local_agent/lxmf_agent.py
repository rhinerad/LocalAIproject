#!/usr/bin/env python3
"""Opt-in LXMF transport for the Equal Shares local agent.

The localhost HTTP app remains on 127.0.0.1. This process is a separate LXMF
peer that converts authenticated Sideband messages into the same history shape
used by the GUI, calls agent.answer(), and sends the final answer back.

No model runs on the phone and this module never starts a render.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import queue
import re
import signal
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

HERE = Path(__file__).resolve().parent
VENDOR = HERE / "vendor"
# A previous portable bundle can leave this optional copy unreadable under a
# different Windows security principal. The normal Python installation carries
# the pinned RNS/LXMF packages too, so never shadow it with an unreadable path.
try:
    _vendor_rns_readable = (VENDOR / "RNS" / "__init__.py").is_file()
    if _vendor_rns_readable:
        with (VENDOR / "RNS" / "__init__.py").open("rb"):
            pass
except OSError:
    _vendor_rns_readable = False
if _vendor_rns_readable:
    sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(HERE))

import agent
import media_queue
import phone_scheduler
import remote_security
import router as model_router
import store
import tools

RUNTIME = HERE / "runtime" / "lxmf"
IDENTITY_FILE = RUNTIME / "identity"
ROUTER_STORAGE = RUNTIME / "router"
PAIRINGS_FILE = RUNTIME / "paired_identities.json"
AUDIT_FILE = RUNTIME / "remote_tool_audit.jsonl"
ATTACHMENT_AUDIT_FILE = RUNTIME / "attachment_audit.jsonl"
OUTBOUND_AUDIT_FILE = RUNTIME / "outbound_delivery_audit.jsonl"
MEDIA_COMPLETION_AUDIT_FILE = RUNTIME / "media_completion_delivery.jsonl"
UPLOADS_DIR = HERE / "uploads" / "lxmf"
MAX_CHUNK_BYTES = 3500
MAX_ATTACHMENT_BYTES = 75 * 1024 * 1024
# Kept as literals so BridgeCore stays independently testable without loading
# RNS/LXMF. They match LXMF.FIELD_FILE_ATTACHMENTS/IMAGE/AUDIO.
FIELD_FILE_ATTACHMENTS = 0x05
FIELD_IMAGE = 0x06
FIELD_AUDIO = 0x07
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
# A fresh Sideband client may join Wi-Fi after this process starts. Re-announce
# occasionally so it can resolve this delivery destination without requiring a
# manual bridge restart. This is presence discovery only; it sends no chat data.
ANNOUNCE_INTERVAL_SECONDS = 30
PROTOCOL = "equal-shares-agent/1"
_instance_mutex = None
_CANCEL_ACTIVE_SCHEDULE_RE = re.compile(
    r"^\s*(?:please\s+)?(?:cancel|stop|end)\s+(?:the\s+)?"
    r"(?:active|current|ongoing)?\s*(?:phone\s+)?(?:message\s+)?"
    r"schedule(?:s)?[.!]?\s*$", re.IGNORECASE)


def _hex(value) -> str:
    if isinstance(value, bytes):
        return value.hex()
    return str(value or "").strip().lower()


def _message_text(message) -> str:
    method = getattr(message, "content_as_string", None)
    if callable(method):
        text = method()
        return text if isinstance(text, str) else ""
    content = getattr(message, "content", b"")
    if isinstance(content, bytes):
        try:
            return content.decode("utf8")
        except UnicodeDecodeError:
            return ""
    return str(content or "")


def _request_id(message) -> str:
    for name in ("hash", "message_id", "transient_id"):
        value = getattr(message, name, None)
        if value:
            return _hex(value)
    return f"local-{time.time_ns():x}"


def _safe_filename(value: object, fallback: str) -> str:
    name = Path(str(value or "")).name
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return name[:160] or fallback


def _attachment_kind(path: Path, suggested: str) -> str:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return suggested


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf8", newline="") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        fh.flush()


def choose_delivery_method(router, RNS, LXMF, recipient_hash: bytes):
    """Choose Sideband's safe direct/opportunistic delivery policy.

    A direct link is best while the phone is actively talking to the bridge.
    After that link closes, a compact scheduled message can use the ratchet
    established by the paired conversation as an opportunistic packet.  The
    previous unconditional DIRECT setting made delayed messages wait for a
    new link and let the scheduler mistake router submission for delivery.
    """
    try:
        has_link = bool(router.delivery_link_available(recipient_hash))
        has_ratchet = RNS.Identity.current_ratchet_id(recipient_hash) is not None
        if not has_link and has_ratchet:
            return LXMF.LXMessage.OPPORTUNISTIC
    except Exception:
        # A live link is the conservative fallback if route introspection is
        # temporarily unavailable. handle_outbound will still report failure.
        pass
    return LXMF.LXMessage.DIRECT


def chunk_utf8(text: str, max_bytes: int = MAX_CHUNK_BYTES) -> list[str]:
    """Split without corrupting UTF-8, preferring whitespace boundaries."""
    if max_bytes < 16:
        raise ValueError("max_bytes is too small")
    text = str(text or "")
    if not text:
        return [""]
    chunks: list[str] = []
    remaining = text
    while len(remaining.encode("utf8")) > max_bytes:
        raw = remaining.encode("utf8")[:max_bytes]
        candidate = raw.decode("utf8", errors="ignore")
        split = max(candidate.rfind("\n"), candidate.rfind(" "))
        if split >= max(16, len(candidate) // 2):
            candidate = candidate[:split + 1]
        if not candidate:
            candidate = remaining[0]
        chunks.append(candidate)
        remaining = remaining[len(candidate):]
    chunks.append(remaining)
    return chunks


class BridgeCore:
    """Transport-independent Sideband turn adapter, directly mockable in tests."""

    def __init__(self, send: Callable[[bytes, str, dict], None],
                 *, agent_module=agent, store_module=store,
                 security_module=remote_security,
                 pairings_path: Path = PAIRINGS_FILE,
                 audit_path: Path = AUDIT_FILE,
                 unpaired_audit_path: Path = remote_security.UNPAIRED_AUDIT,
                 uploads_dir: Path = UPLOADS_DIR,
                 attachment_audit_path: Path = ATTACHMENT_AUDIT_FILE,
                 media_completion_audit_path: Path = MEDIA_COMPLETION_AUDIT_FILE,
                 choose_model: Callable[[dict], str] | None = None):
        self.send = send
        self.agent = agent_module
        self.store = store_module
        self.security = security_module
        self.pairings_path = pairings_path
        self.audit_path = audit_path
        self.unpaired_audit_path = unpaired_audit_path
        self.uploads_dir = uploads_dir
        self.attachment_audit_path = attachment_audit_path
        self.media_completion_audit_path = media_completion_audit_path
        self.choose_model = choose_model or self._choose_model
        self._seen = set()
        self._seen_order = deque(maxlen=1024)

    @staticmethod
    def _choose_model(pair: dict) -> str:
        pinned = str(pair.get("model") or "").strip()
        if pinned:
            installed = {m["name"] for m in model_router.chat_models()}
            if pinned in installed:
                return pinned
        return model_router.decide("auto").model or ""

    # ── scheduled outbound messages ───────────────────────────────────────
    #
    # phone_scheduler stores the jobs; this supplies the delivery half. Without
    # this drain the scheduler was inert: jobs were created and never sent,
    # which is exactly the failure the operator saw.
    #
    # A schedule is revoked the moment its pairing is deactivated — raising
    # ScheduleBlocked marks the job blocked rather than retrying forever.

    def _scheduled_send(self, identity: str, message: str, meta: dict) -> None:
        pair = self.security.get_pair(identity, self.pairings_path)
        if not pair:
            raise phone_scheduler.ScheduleBlocked(
                "the paired phone identity is no longer active")
        self._reply(bytes.fromhex(identity), message,
                    str(meta.get("job_id", "scheduled")),
                    str(pair.get("conversation_id", "")), "scheduled")

    def drain_scheduled(self, *, now: float | None = None) -> list[dict]:
        """Queue every due scheduled message once. Safe to call on a timer."""
        try:
            return phone_scheduler.dispatch_due(self._scheduled_send, now=now)
        except Exception as exc:                       # never kill the bridge loop
            print(f"  scheduled-message dispatch error: {type(exc).__name__}: {exc}")
            return []

    # ── completed media return path ───────────────────────────────────────
    #
    # Media workers deliberately run outside the chat request.  A queued photo
    # or video therefore needs a small, auditable bridge handoff after it is
    # complete.  This reader only considers jobs with bridge-injected routing
    # metadata, except for a narrowly-scoped recovery of older Sideband upload
    # jobs by matching their immutable request-id upload folder to the existing
    # attachment audit.  Desktop jobs never qualify.

    def _delivered_media_ids(self) -> set[str]:
        try:
            return {str(json.loads(line).get("job_id", ""))
                    for line in self.media_completion_audit_path.read_text(
                        encoding="utf-8").splitlines() if line.strip()}
        except (OSError, ValueError, json.JSONDecodeError):
            return set()

    def _recover_sideband_media_target(self, job: dict) -> tuple[str, str] | None:
        """Recover one pre-metadata Sideband job using audit-only linkage."""
        args = job.get("args") or {}
        paths = list(args.get("images") or [])
        paths.extend([args.get("path", ""), args.get("video_path", "")])
        prefixes = {Path(str(path)).parent.name.lower()[:32] for path in paths if path}
        if not prefixes:
            return None
        try:
            rows = [json.loads(line) for line in self.attachment_audit_path.read_text(
                encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        for row in reversed(rows):
            request_id = str(row.get("request_id") or "")
            identity = str(row.get("identity") or "")
            if request_id[:32].lower() in prefixes:
                try:
                    return self.security.normalise_identity(identity), request_id
                except ValueError:
                    return None
        return None

    @staticmethod
    def _media_reply_text(job: dict) -> str:
        raw = str(job.get("result") or "")
        try:
            data = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return "Media analysis completed, but its local result could not be read."
        analysis = data.get("analysis") or data.get("action_log") or data.get("transcript")
        if analysis:
            text = str(analysis).strip()
            # LXMF chunking handles long useful results. A hard ceiling avoids
            # a malformed worker result turning into an unbounded radio send.
            if len(text) > 30000:
                text = text[:30000].rstrip() + "\n\n[Analysis truncated at the transport limit.]"
            return "Media analysis completed:\n\n" + text
        reason = str(data.get("reason") or "").strip()
        return ("Media analysis completed but was unavailable" +
                (f": {reason}" if reason else "."))

    def drain_media_completions(self) -> list[str]:
        """Deliver each eligible completed media job to its paired phone once."""
        delivered = self._delivered_media_ids()
        sent: list[str] = []
        done_dir = media_queue.QUEUE_ROOT / "done"
        try:
            paths = sorted(done_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
        except OSError:
            return sent
        for path in paths:
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
                job_id = str(job.get("id") or "")
                if not job_id or job_id in delivered:
                    continue
                args = job.get("args") or {}
                identity = str(args.get("__remote_media_identity") or "")
                request_id = str(args.get("__remote_media_request_id") or "")
                cid = str(args.get("__remote_media_conversation_id") or "")
                if not identity:
                    recovered = self._recover_sideband_media_target(job)
                    if not recovered:
                        continue
                    identity, request_id = recovered
                identity = self.security.normalise_identity(identity)
                pair = self.security.get_pair(identity, self.pairings_path)
                if not pair:
                    continue
                cid = cid or str(pair.get("conversation_id") or "")
                if not cid:
                    continue
                reply = self._media_reply_text(job)
                self.store.append(cid, "assistant", reply,
                                  meta={"remote_identity": identity,
                                        "request_id": request_id,
                                        "media_job_id": job_id}, source="phone")
                self._reply(bytes.fromhex(identity), reply,
                            request_id or f"media-{job_id}", cid, "media_result")
                _append_jsonl(self.media_completion_audit_path, {
                    "at": time.time(), "event": "media_completion_delivered",
                    "job_id": job_id, "identity": identity,
                    "request_id": request_id,
                    "result_sha256": hashlib.sha256(
                        str(job.get("result") or "").encode("utf-8")).hexdigest(),
                })
                delivered.add(job_id)
                sent.append(job_id)
            except Exception as exc:
                print(f"  media-completion delivery skipped: {type(exc).__name__}: {exc}")
        return sent

    def _reply(self, source_hash: bytes, text: str, request_id: str,
               conversation_id: str = "", kind: str = "final") -> None:
        parts = chunk_utf8(text)
        for index, part in enumerate(parts, 1):
            self.send(source_hash, part, {
                "equal_shares_agent": {
                    "protocol": PROTOCOL,
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "kind": kind,
                    "sequence": index,
                    "total": len(parts),
                    "final": index == len(parts),
                }
            })

    def _save_attachment(self, identity: str, request_id: str, kind: str,
                         name: object, data: object, fallback: str) -> dict | None:
        """Persist one paired-phone media item, never its bytes in a chat record."""
        if not isinstance(data, bytes) or not data or len(data) > MAX_ATTACHMENT_BYTES:
            return None
        safe_name = _safe_filename(name, fallback)
        # A request-id directory is immutable; an existing file is never replaced.
        folder = self.uploads_dir / request_id[:32]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name
        if path.exists():
            stem, suffix = path.stem, path.suffix
            path = folder / f"{stem}_{hashlib.sha256(data).hexdigest()[:10]}{suffix}"
        with path.open("xb") as fh:
            fh.write(data)
        kind = _attachment_kind(path, kind)
        item = {
            "kind": kind,
            "name": path.name,
            "path": str(path.resolve()),
            "bytes": len(data),
        }
        _append_jsonl(self.attachment_audit_path, {
            "at": time.time(), "event": "received_attachment",
            "identity": identity, "request_id": request_id,
            "kind": kind, "name": path.name, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
        return item

    def _receive_attachments(self, message, identity: str, request_id: str) -> list[dict]:
        """Decode the stock Sideband field shapes from a paired sender only."""
        fields = getattr(message, "fields", None)
        if not isinstance(fields, dict):
            return []
        items: list[dict] = []
        attachments = fields.get(FIELD_FILE_ATTACHMENTS, [])
        if isinstance(attachments, (list, tuple)):
            for index, attachment in enumerate(attachments, 1):
                if isinstance(attachment, (list, tuple)) and len(attachment) >= 2:
                    item = self._save_attachment(identity, request_id, "file",
                                                 attachment[0], attachment[1],
                                                 f"attachment_{index}")
                    if item:
                        items.append(item)
        image = fields.get(FIELD_IMAGE)
        if isinstance(image, (list, tuple)) and len(image) >= 2:
            fmt = str(image[0] or "webp").lower()
            ext = fmt if re.fullmatch(r"[a-z0-9]{1,8}", fmt) else "webp"
            item = self._save_attachment(identity, request_id, "image",
                                         f"sideband_image.{ext}", image[1],
                                         "sideband_image.webp")
            if item:
                items.append(item)
        audio = fields.get(FIELD_AUDIO)
        if isinstance(audio, (list, tuple)) and len(audio) >= 2:
            # Sideband's normal microphone path uses Opus-in-Ogg. Preserve a
            # conservative .ogg label; unsupported codecs remain an honest
            # workstation-tool error instead of fabricated transcription.
            item = self._save_attachment(identity, request_id, "audio",
                                         "sideband_audio.ogg", audio[1],
                                         "sideband_audio.ogg")
            if item:
                items.append(item)
        return items

    @staticmethod
    def _attachment_instructions(items: list[dict]) -> str:
        if not items:
            return ""
        tool_for = {
            "image": "Call see_image on this path before describing it.",
            "audio": "Call audio_measure, then transcribe if speech is likely.",
            "video": "Call analyze_video or extract_video_actions before describing it.",
            "file": "Inspect this local file only with an appropriate allowed tool.",
        }
        lines = ["\n\n--- Sideband attachments (paths only; use tools first) ---"]
        for item in items:
            lines.append(f"{item['kind']}: {item['path']}\n{tool_for.get(item['kind'], tool_for['file'])}")
        return "\n".join(lines)

    def _phone_event(self, source_hash: bytes, request_id: str,
                     conversation_id: str, kind: str, payload: str) -> None:
        """Translate safe progress milestones to ordinary Sideband messages.

        Full token streaming is intentionally not mirrored: it makes a
        store-and-forward LXMF conversation noisy and can expose partial model
        reasoning. Tool arguments/results may contain local paths or content, so
        the phone receives only a tool name and a completion state.
        """
        status = ""
        if kind == "route":
            try:
                route = json.loads(payload)
                tier = str(route.get("tier", "local")).upper()
                reason = str(route.get("reason", ""))
                if tier == "CPU" and ("ComfyUI" in reason or "GPU reserved" in reason):
                    status = "Working on the workstation (temporary CPU fallback while ComfyUI reserves the GPU)…"
                else:
                    status = f"Working on the workstation ({tier} model)…"
            except (TypeError, ValueError, json.JSONDecodeError):
                status = "Working on the workstation…"
        elif kind == "tool":
            try:
                name = str(json.loads(payload).get("tool", "local tool"))
            except (TypeError, ValueError, json.JSONDecodeError):
                name = "local tool"
            name = re.sub(r"[^A-Za-z0-9_-]+", "", name)[:64] or "local tool"
            status = f"Using local tool: {name}…"
        elif kind == "tool_result":
            status = "Local tool finished; preparing the answer…"
        elif kind == "error":
            status = "A workstation step failed safely; preparing the error details…"
        if status:
            self._reply(source_hash, status, request_id, conversation_id, "status")

    def _cancel_active_phone_schedules(self, source_hash: bytes, identity: str,
                                       request_id: str, cid: str, context, meta: dict) -> bool:
        """Handle the exact phone cancellation command without an LLM delay.

        This is deliberately narrow: the verified sender can only cancel its
        own currently-active jobs, and the existing tools.py scheduler boundary
        still injects the identity and writes the remote-tool audit record.
        """
        active = [job for job in phone_scheduler.list_for_identity(identity)
                  if job.get("status") == "active"]
        if not active:
            reply = "There is no active phone message schedule to cancel."
        else:
            for job in active:
                tools.call("cancel_phone_schedule", {"job_id": job["id"]}, context=context)
            count = len(active)
            reply = ("Cancelled the active phone message schedule."
                     if count == 1 else
                     f"Cancelled {count} active phone message schedules.")
        self.store.append(cid, "assistant", reply, meta=meta, source="phone")
        self._reply(source_hash, reply, request_id, cid, "final")
        return True

    def handle(self, message) -> None:
        source_hash = getattr(message, "source_hash", b"")
        request_id = _request_id(message)
        if request_id in self._seen:
            return
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen.discard(self._seen_order[0])
        self._seen.add(request_id)
        self._seen_order.append(request_id)

        pair = self.security.get_pair(source_hash, self.pairings_path)
        if not pair:
            # Keep only the verified LXMF delivery address and request ID. This
            # lets the local operator pair the right Sideband identity without
            # retaining content from an untrusted message.
            self.security.record_unpaired_attempt(
                source_hash, request_id, self.unpaired_audit_path)
            self._reply(source_hash,
                        "Not authorised. Pair this Sideband LXMF address on the workstation first.",
                        request_id, kind="refused")
            return

        identity = self.security.normalise_identity(source_hash)
        attachments = self._receive_attachments(message, identity, request_id)
        text = _message_text(message).strip() + self._attachment_instructions(attachments)
        if not text:
            self._reply(source_hash, "I received an empty or non-text message.",
                        request_id, pair.get("conversation_id", ""), "refused")
            return

        cid = str(pair.get("conversation_id") or "")
        conv = self.store.load(cid) if cid else None
        if not conv:
            model = self.choose_model(pair)
            if not model:
                self._reply(source_hash,
                            "No local chat model is available on the workstation.",
                            request_id, kind="error")
                return
            conv = self.store.create(text, model=model)
            cid = conv["id"]
            self.security.set_conversation(source_hash, cid, self.pairings_path)

        meta = {"remote_identity": identity, "request_id": request_id}
        if attachments:
            meta["attachments"] = [{k: item[k] for k in ("kind", "name", "path", "bytes")}
                                   for item in attachments]
        self.store.append(cid, "user", text, meta=meta, source="phone")
        conv = self.store.load(cid)
        history = [{"role": m["role"], "content": m["content"]}
                   for m in conv.get("messages", [])]
        context = self.security.context_for(
            source_hash, cid, request_id, self.pairings_path, self.audit_path)
        if not attachments and _CANCEL_ACTIVE_SCHEDULE_RE.fullmatch(text):
            self._cancel_active_phone_schedules(
                source_hash, identity, request_id, cid, context, meta)
            return
        # A blank per-identity model means automatic routing, not "pin the
        # first model that happened to be available".  A phone chat can first
        # arrive while ComfyUI owns VRAM, in which case its stored conversation
        # model is necessarily the CPU fallback.  Passing that stored value on
        # every later turn made the fallback sticky even after the GPU became
        # available.  Preserve explicit identity pins, but let an automatic
        # identity re-evaluate the normal GPU/CPU policy per message.
        identity_model = str(pair.get("model") or "").strip()
        try:
            reply = self.agent.answer(
                history,
                on_event=lambda kind, payload: self._phone_event(
                    source_hash, request_id, cid, kind, payload),
                model=identity_model or None, tool_context=context)
        except Exception as exc:
            self._reply(source_hash,
                        f"The workstation agent failed safely: {type(exc).__name__}: {exc}",
                        request_id, cid, "error")
            return
        self.store.append(cid, "assistant", reply, meta=meta, source="phone")
        self._reply(source_hash, reply, request_id, cid, "final")


class LXMFBridge:
    def __init__(self, configdir: str | None = None):
        try:
            import RNS
            import LXMF
        except ImportError as exc:
            raise RuntimeError(
                "RNS/LXMF are missing. Restore local_agent/vendor from "
                "requirements-lxmf.txt before starting the bridge.") from exc
        self.RNS = RNS
        self.LXMF = LXMF
        RUNTIME.mkdir(parents=True, exist_ok=True)
        ROUTER_STORAGE.mkdir(parents=True, exist_ok=True)
        self.reticulum = RNS.Reticulum(configdir=configdir)
        self.router = LXMF.LXMRouter(storagepath=str(ROUTER_STORAGE))
        self.identity = self._load_identity()
        self.source = self.router.register_delivery_identity(
            self.identity, display_name="Equal Shares Agent")
        if self.source is None:
            raise RuntimeError("LXMF did not register the delivery identity")
        self.core = BridgeCore(self._send)
        self.inbox: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._worker, name="lxmf-agent-worker",
                                       daemon=True)
        self.router.register_delivery_callback(self.inbox.put)

    def _load_identity(self):
        if IDENTITY_FILE.is_file():
            identity = self.RNS.Identity.from_file(str(IDENTITY_FILE))
            if identity is None:
                raise RuntimeError(f"invalid persistent LXMF identity: {IDENTITY_FILE}")
            return identity
        identity = self.RNS.Identity()
        if not identity.to_file(str(IDENTITY_FILE)):
            raise RuntimeError(f"could not save LXMF identity: {IDENTITY_FILE}")
        try:
            os.chmod(IDENTITY_FILE, 0o600)
        except OSError:
            pass
        return identity

    @property
    def address(self) -> str:
        return _hex(self.source.hash)

    def _send(self, recipient_hash: bytes, text: str, fields: dict) -> None:
        identity = self.RNS.Identity.recall(recipient_hash)
        if identity is None:
            raise RuntimeError(f"cannot recall recipient identity {_hex(recipient_hash)}")
        destination = self.RNS.Destination(
            identity, self.RNS.Destination.OUT, self.RNS.Destination.SINGLE,
            "lxmf", "delivery")
        desired_method = choose_delivery_method(
            self.router, self.RNS, self.LXMF, recipient_hash)
        message = self.LXMF.LXMessage(
            destination, self.source, text, "Equal Shares Agent", fields=fields,
            desired_method=desired_method, include_ticket=True)
        message.register_delivery_callback(
            lambda delivered: self._record_outbound_result(
                "delivered", recipient_hash, delivered, fields))
        message.register_failed_callback(
            lambda failed: self._record_outbound_result(
                "failed", recipient_hash, failed, fields))
        self.router.handle_outbound(message)

    def _record_outbound_result(self, outcome: str, recipient_hash: bytes,
                                message, fields: dict) -> None:
        """Persist final LXMF outcome; router submission is not delivery proof."""
        agent_fields = fields.get("equal_shares_agent", {}) if isinstance(fields, dict) else {}
        _append_jsonl(OUTBOUND_AUDIT_FILE, {
            "at": time.time(),
            "event": outcome,
            "recipient": _hex(recipient_hash),
            "message_hash": _hex(getattr(message, "hash", None)),
            "method": getattr(message, "method", None),
            "desired_method": getattr(message, "desired_method", None),
            "state": getattr(message, "state", None),
            "kind": str(agent_fields.get("kind", "")),
            "request_id": str(agent_fields.get("request_id", "")),
        })

    def _worker(self) -> None:
        while not self.stop_event.is_set():
            try:
                message = self.inbox.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self.core.handle(message)
            except Exception as exc:
                print(f"LXMF inbound turn failed safely: {type(exc).__name__}: {exc}",
                      file=sys.stderr, flush=True)
            finally:
                self.inbox.task_done()

    def run(self, run_seconds: float = 0) -> None:
        self.worker.start()
        self.router.announce(self.source.hash)
        print("Equal Shares Sideband bridge")
        print(f"  LXMF address : {self.address}")
        print(f"  paired file  : {PAIRINGS_FILE}")
        print("  HTTP remains : http://127.0.0.1:8760")
        print("  Ctrl-C to stop")
        started = time.monotonic()
        next_announce = started + ANNOUNCE_INTERVAL_SECONDS
        while not self.stop_event.wait(1.0):
            now = time.monotonic()
            # Scheduler ownership is intentionally transport-agnostic in
            # BridgeCore.  The old direct lookup on LXMFBridge crashed the
            # bridge one second after startup, before it could deliver a job.
            self.core.drain_scheduled()
            self.core.drain_media_completions()
            if now >= next_announce:
                self.router.announce(self.source.hash)
                next_announce = now + ANNOUNCE_INTERVAL_SECONDS
            if run_seconds and now - started >= run_seconds:
                self.stop()

    def stop(self) -> None:
        self.stop_event.set()


def _claim_single_instance() -> bool:
    global _instance_mutex
    if os.name != "nt":
        return True
    import ctypes
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, "Local\\EqualSharesLXMFBridge")
    if not handle:
        raise OSError(ctypes.get_last_error(), "could not create LXMF bridge mutex")
    if ctypes.get_last_error() == 183:
        kernel32.CloseHandle(handle)
        return False
    _instance_mutex = handle
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sideband/LXMF transport for the local agent")
    parser.add_argument("--rns-config", default=None,
                        help="optional Reticulum config directory; default uses the normal RNS config")
    parser.add_argument("--check", action="store_true",
                        help="check installed modules and pairing data without starting RNS")
    parser.add_argument("--run-seconds", type=float, default=0,
                        help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.check:
        import RNS
        import LXMF
        print(json.dumps({
            "rns": RNS.__version__, "lxmf": LXMF.__version__,
            "paired_active": sum(1 for r in remote_security.load_pairings()["identities"].values()
                                 if r.get("active")),
            "http_binding": "127.0.0.1:8760",
        }, indent=2))
        return 0
    if not _claim_single_instance():
        print("The Equal Shares LXMF bridge is already running.")
        return 0
    bridge = LXMFBridge(args.rns_config)
    signal.signal(signal.SIGINT, lambda *_: bridge.stop())
    signal.signal(signal.SIGTERM, lambda *_: bridge.stop())
    bridge.run(max(0, args.run_seconds))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
