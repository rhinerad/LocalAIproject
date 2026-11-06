#!/usr/bin/env python3
"""Privacy-preserving, idle-only encrypted feedback records.

Nothing is written to disk at submit time.  A daemon worker writes an AES-256-GCM
envelope only after the local agent is not streaming and the GPU is not claimed.
The default record keeps a query fingerprint and an operator-written rule, never
the raw chat.  ``full_sanitized`` is an explicit opt-in mode for later curation.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import queue
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTOGRAPHY_AVAILABLE = True
    _CRYPTOGRAPHY_REASON = ""
except ImportError:
    AESGCM = None  # type: ignore[assignment,misc]
    _CRYPTOGRAPHY_AVAILABLE = False
    _CRYPTOGRAPHY_REASON = (
        "cryptography is not installed (pip install cryptography). "
        "Feedback records cannot be encrypted or stored."
    )

import router
import store

HERE = Path(__file__).resolve().parent
STORE_DIR = HERE / "feedback_store"
KEY_FILE = HERE / "runtime" / "feedback_keys" / "feedback_key.dpapi"
# Feedback is deliberately bounded.  The worker may only encrypt while the
# machine is idle; an unbounded in-memory retry queue turned a prolonged busy
# GPU or key-service fault into a silent RAM leak.
MAX_PENDING_RECORDS = 256
QUARANTINE_DIR = HERE / "runtime" / "feedback_quarantine"
_PENDING: queue.Queue[dict] = queue.Queue(maxsize=MAX_PENDING_RECORDS)
_WORKER: threading.Thread | None = None
_WORKER_LOCK = threading.Lock()
_STOP = threading.Event()
_LAST_ERROR = ""
_DROPPED_OVERFLOW = 0
_QUARANTINED = 0
_FAILURES: dict[str, int] = {}
MAX_ENCRYPTION_FAILURES = 3
_MODES = frozenset({"rule_only", "full_sanitized"})
_RATINGS = frozenset({"positive", "negative"})
_CATEGORIES = frozenset({"prompt_crafting", "comfyui_workflow", "story_script", "tool_execution"})
_PATH_RE = re.compile(r"(?i)(?:[A-Z]:\\(?:Users\\[^\\\s]+|Windows|Program Files)[^\s\"']*|\\\\[^\s\"']+)")
_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_SECRET_RE = re.compile(r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password)\b\s*[:=]\s*([^\s,;]+)")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _dpapi_protect(data: bytes) -> bytes:
    """Protect a key for the current Windows user without an extra package."""
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is required for the local feedback key")
    source = ctypes.create_string_buffer(data, len(data))
    inp = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    out = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_wchar_p,
                                         ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_uint32, ctypes.POINTER(_DataBlob)]
    crypt32.CryptProtectData.restype = ctypes.c_int
    if not crypt32.CryptProtectData(ctypes.byref(inp), "Local Agent feedback key", None,
                                    None, None, 0x1, ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "DPAPI protection failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is required for the local feedback key")
    source = ctypes.create_string_buffer(data, len(data))
    inp = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    out = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [ctypes.POINTER(_DataBlob), ctypes.c_void_p,
                                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                           ctypes.c_uint32, ctypes.POINTER(_DataBlob)]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    if not crypt32.CryptUnprotectData(ctypes.byref(inp), None, None, None, None, 0x1,
                                      ctypes.byref(out)):
        raise OSError(ctypes.get_last_error(), "DPAPI unprotection failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _key() -> bytes:
    supplied = os.environ.get("LOCAL_AGENT_FEEDBACK_KEY", "").strip()
    if supplied:
        try:
            value = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        except Exception as exc:
            raise RuntimeError("LOCAL_AGENT_FEEDBACK_KEY is not valid base64") from exc
        if len(value) != 32:
            raise RuntimeError("LOCAL_AGENT_FEEDBACK_KEY must decode to exactly 32 bytes")
        return value
    if KEY_FILE.is_file():
        value = _dpapi_unprotect(KEY_FILE.read_bytes())
        if len(value) != 32:
            raise RuntimeError("stored feedback key has an invalid length")
        return value
    value = os.urandom(32)
    # Desktop launches have a loaded Windows profile, so DPAPI is the normal
    # zero-configuration path.  Some headless/service contexts deliberately do
    # not expose a profile; fail closed there instead of persisting a plaintext
    # key.  An operator may explicitly supply LOCAL_AGENT_FEEDBACK_KEY for such
    # a service account.
    _atomic_write(KEY_FILE, _dpapi_protect(value))
    return value


def sanitize(value: object) -> str:
    """Remove common local PII/secrets before an opt-in payload is retained."""
    text = str(value or "")
    def path_repl(match: re.Match) -> str:
        raw = match.group(0)
        return "<SYS_ROOT>" if re.match(r"(?i)[A-Z]:\\(?:Windows|Program Files)", raw) else "<WORKSPACE_ROOT>"
    text = _PATH_RE.sub(path_repl, text)
    text = _EMAIL_RE.sub("<EMAIL>", text)
    return _SECRET_RE.sub(lambda m: f"{m.group(1)}=<REDACTED>", text)


def _latest(conversation: dict, role: str) -> str:
    for message in reversed(conversation.get("messages", [])):
        if message.get("role") == role:
            return str(message.get("content", ""))
    return ""


def _category(query: str, explicit: str = "") -> str:
    if explicit in _CATEGORIES:
        return explicit
    low = query.lower()
    if "comfyui" in low or "workflow" in low:
        return "comfyui_workflow"
    if "prompt" in low:
        return "prompt_crafting"
    if "story" in low or "scene" in low or "screenplay" in low:
        return "story_script"
    return "tool_execution"


def build_record(conversation_id: str, *, rating: str, distilled_rule: str = "",
                 mode: str = "rule_only", category: str = "") -> dict:
    if rating not in _RATINGS:
        raise ValueError("rating must be positive or negative")
    if mode not in _MODES:
        raise ValueError("mode must be rule_only or full_sanitized")
    conv = store.load(conversation_id)
    if not conv:
        raise ValueError("conversation not found")
    query, output = _latest(conv, "user"), _latest(conv, "assistant")
    if not query or not output:
        raise ValueError("conversation needs both a user request and assistant response")
    rule = " ".join(str(distilled_rule or "").split())[:600]
    if mode == "rule_only" and rating == "positive" and not rule:
        # A thumbs-up may be useful for exemplar scoring, but it is never a
        # general learning signal in the rule-only store.
        rule = ""
    fingerprint = hashlib.sha256(query.encode("utf8", "replace")).hexdigest()
    record = {
        "id": f"fb_{int(time.time() * 1000)}_{uuid.uuid4().hex[:12]}",
        "timestamp": _utc(), "conversation_id": str(conversation_id)[:40],
        "message_id": hashlib.sha256(output.encode("utf8", "replace")).hexdigest()[:16],
        "mode": mode, "query_fingerprint": fingerprint, "distilled_rule": rule,
        "rating": rating, "category": _category(query, category), "is_encrypted": False,
    }
    if mode == "full_sanitized":
        record["sanitized_payload"] = {"prompt": sanitize(query), "model_output": sanitize(output)}
    else:
        record["sanitized_payload"] = {}
    return record


def is_idle() -> bool:
    """Conservative idle predicate: no streaming chat and no GPU claimant."""
    try:
        return not router.chat_busy() and not router.gpu_busy()[0]
    except Exception:
        return False


def _encrypt(record: dict) -> dict:
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise RuntimeError(_CRYPTOGRAPHY_REASON)
    nonce = os.urandom(12)
    raw = json.dumps({**record, "is_encrypted": True}, ensure_ascii=False,
                     separators=(",", ":")).encode("utf8")
    cipher = AESGCM(_key()).encrypt(nonce, raw, record["id"].encode("utf8"))
    return {"version": 1, "algorithm": "AES-256-GCM", "id": record["id"],
            "is_encrypted": True, "nonce": base64.b64encode(nonce).decode("ascii"),
            "ciphertext": base64.b64encode(cipher).decode("ascii")}


def decrypt_envelope(path: Path) -> dict:
    if not _CRYPTOGRAPHY_AVAILABLE:
        return {"available": False, "reason": _CRYPTOGRAPHY_REASON,
                "install": "pip install cryptography"}
    envelope = json.loads(path.read_text(encoding="utf8"))
    if envelope.get("algorithm") != "AES-256-GCM" or not envelope.get("is_encrypted"):
        raise ValueError("feedback record is not an AES-256-GCM envelope")
    nonce = base64.b64decode(envelope["nonce"])
    cipher = base64.b64decode(envelope["ciphertext"])
    raw = AESGCM(_key()).decrypt(nonce, cipher, str(envelope["id"]).encode("utf8"))
    return json.loads(raw)


def _quarantine(record: dict, *, reason: str) -> None:
    """Write diagnostic metadata only — never a plaintext feedback payload."""
    global _QUARANTINED
    record_id = str(record.get("id", "unknown"))[:100]
    digest = hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str, separators=(",", ":")).encode("utf8")
    ).hexdigest()
    event = {"at": _utc(), "record_id": record_id, "reason": reason[:300],
             "record_sha256": digest}
    try:
        _atomic_write(QUARANTINE_DIR / f"{record_id}_{uuid.uuid4().hex[:8]}.json",
                      json.dumps(event, indent=2).encode("utf8"))
    except Exception:
        # A full/unavailable disk must not turn a bounded queue overflow back
        # into an exception path that preserves unbounded private data in RAM.
        # The record is still dropped; no plaintext fallback is ever written.
        pass
    finally:
        _QUARANTINED += 1


def enqueue(record: dict) -> bool:
    """Queue feedback without permitting unlimited RAM growth.

    The newest record wins on overflow.  The displaced record leaves only a
    non-sensitive quarantine fingerprint, never an unencrypted payload.
    """
    global _DROPPED_OVERFLOW, _LAST_ERROR
    try:
        _PENDING.put_nowait(record)
        return True
    except queue.Full:
        try:
            displaced = _PENDING.get_nowait()
        except queue.Empty:  # Another thread drained it between Full/get.
            displaced = None
        if displaced is not None:
            _quarantine(displaced, reason="pending queue overflow; oldest record dropped")
            _DROPPED_OVERFLOW += 1
        try:
            _PENDING.put_nowait(record)
            _LAST_ERROR = "feedback queue overflow; oldest record quarantined"
            return True
        except queue.Full:
            _quarantine(record, reason="pending queue overflow; new record dropped")
            _DROPPED_OVERFLOW += 1
            _LAST_ERROR = "feedback queue overflow; new record quarantined"
            return False


def flush_pending(*, force: bool = False) -> int:
    """Encrypt queued records. ``force`` exists for deterministic unit tests only."""
    if not force and not is_idle():
        return 0
    global _LAST_ERROR
    written = 0
    while True:
        try:
            record = _PENDING.get_nowait()
        except queue.Empty:
            break
        try:
            envelope = _encrypt(record)
            _atomic_write(STORE_DIR / f"{record['id']}.json", json.dumps(envelope, indent=2).encode("utf8"))
            written += 1
            _LAST_ERROR = ""
            _FAILURES.pop(str(record.get("id", "")), None)
        except Exception as exc:
            # A temporary DPAPI/key service outage may clear on the next idle
            # pass.  A permanently malformed/poison record must not retry
            # forever, however: retain it for a bounded three attempts and
            # then quarantine only its fingerprint.
            record_id = str(record.get("id", ""))
            failures = _FAILURES.get(record_id, 0) + 1
            _FAILURES[record_id] = failures
            _LAST_ERROR = f"{type(exc).__name__}: {exc}"
            if failures >= MAX_ENCRYPTION_FAILURES:
                _FAILURES.pop(record_id, None)
                _quarantine(record, reason=f"encryption failed {failures} times: {_LAST_ERROR}")
                continue
            # Space is guaranteed because this record was just removed.  If a
            # concurrent producer wins the slot, handle it through the same
            # bounded overflow policy instead of blocking a worker forever.
            enqueue(record)
            raise
    return written


def _worker() -> None:
    while not _STOP.wait(2.0):
        try:
            flush_pending()
        except Exception:
            # Leave queued records in RAM; never write an unencrypted fallback.
            pass


def start_idle_worker() -> None:
    if not _CRYPTOGRAPHY_AVAILABLE:
        return
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER and _WORKER.is_alive():
            return
        _STOP.clear()
        _WORKER = threading.Thread(target=_worker, name="feedback-idle-encrypt", daemon=True)
        _WORKER.start()


def pending_count() -> int:
    return _PENDING.qsize()


def status() -> dict:
    """Safe operational status for the local-only GUI; contains no record data."""
    if not _CRYPTOGRAPHY_AVAILABLE:
        return {"pending": 0, "idle": True, "last_error": _CRYPTOGRAPHY_REASON,
                "storage": "unavailable", "available": False,
                "install": "pip install cryptography"}
    return {"pending": pending_count(), "idle": is_idle(), "last_error": _LAST_ERROR,
            "overflow_dropped": _DROPPED_OVERFLOW, "quarantined": _QUARANTINED,
            "storage": "AES-256-GCM idle-only"}
