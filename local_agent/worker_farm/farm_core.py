"""Dependency-light, review-only artifact and distillation primitives."""
from __future__ import annotations

import base64
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ALLOWED_WORKFLOWS = frozenset({
    "historical_memory_distillation", "judge_evaluation", "text_preprocess",
    "small_embedding_batch",
})
_PATH_RE = re.compile(r"(?i)(?:[A-Z]:\\|/home/|/Users/)[^\s\"']+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_SECRET_RE = re.compile(r"(?i)\b(api[_ -]?key|token|password|secret)\b\s*[:=]\s*\S+")
_BEARER_RE = re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+\S+")
_URL_CREDENTIAL_RE = re.compile(r"(?i)\b(https?://)[^\s/@:]+:[^\s/@]+@")
_KNOWN_TOKEN_RE = re.compile(r"\b(?:ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|hf_[A-Za-z0-9]{20,})\b")
_MAX_EXTRACTED_CHARS = 500_000
_MAX_SOURCE_BYTES = 25 * 1024 * 1024


class FarmPolicyError(ValueError):
    pass


class _VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in {"script", "style", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data):
        if not self._ignored_depth:
            self.parts.append(data)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _root(value: str | os.PathLike[str] | None = None) -> Path:
    return Path(value or os.environ.get("FARM_ROOT") or Path(__file__).parent).resolve()


def _child(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate != root and root not in candidate.parents:
        raise FarmPolicyError("artifact path escaped its assigned root")
    return candidate


def _read_allowed_source(source: str | os.PathLike[str]) -> tuple[Path, str]:
    path = Path(source).resolve()
    if not path.is_file() or path.suffix.lower() not in {".json", ".html", ".htm", ".txt"}:
        raise FarmPolicyError("source must be an existing JSON, HTML, or text file")
    if path.stat().st_size > _MAX_SOURCE_BYTES:
        raise FarmPolicyError("source exceeds the Phase 1 review-only size limit")
    return path, path.read_text(encoding="utf-8", errors="replace")


def encryption_key(value: str | None = None) -> bytes:
    encoded = value or os.environ.get("FARM_ENCRYPTION_KEY_B64", "")
    try:
        key = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise FarmPolicyError("FARM_ENCRYPTION_KEY_B64 must be valid base64") from exc
    if len(key) != 32:
        raise FarmPolicyError("FARM_ENCRYPTION_KEY_B64 must decode to exactly 32 bytes")
    return key


def sanitize_text(value: str) -> str:
    value = _PATH_RE.sub("<PATH>", str(value))
    value = _EMAIL_RE.sub("<EMAIL>", value)
    value = _BEARER_RE.sub("Authorization: Bearer <REDACTED>", value)
    value = _URL_CREDENTIAL_RE.sub(r"\1<REDACTED>@", value)
    value = _KNOWN_TOKEN_RE.sub("<REDACTED>", value)
    return _SECRET_RE.sub(lambda match: f"{match.group(1)}=<REDACTED>", value)


def extract_transcript_text(source_name: str, raw: str) -> tuple[str, str]:
    """Deterministically flatten JSON/HTML/text exports without following links."""
    suffix = Path(source_name).suffix.lower()
    if suffix == ".json":
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FarmPolicyError("JSON export could not be parsed") from exc
        chunks: list[str] = []
        extracted_chars = 0

        def walk(item) -> None:
            nonlocal extracted_chars
            if extracted_chars >= _MAX_EXTRACTED_CHARS:
                return
            if isinstance(item, str):
                if item.strip():
                    remaining = _MAX_EXTRACTED_CHARS - extracted_chars
                    piece = item[:remaining]
                    chunks.append(piece)
                    extracted_chars += len(piece) + 1
            elif isinstance(item, list):
                for child in item:
                    walk(child)
            elif isinstance(item, dict):
                for child in item.values():
                    walk(child)

        walk(value)
        return "json", "\n".join(chunks)[:_MAX_EXTRACTED_CHARS]
    if suffix in {".html", ".htm"}:
        parser = _VisibleText()
        parser.feed(raw)
        parser.close()
        return "html", "\n".join(part.strip() for part in parser.parts if part.strip())[:_MAX_EXTRACTED_CHARS]
    return "text", raw[:_MAX_EXTRACTED_CHARS]


class EncryptedArtifactStore:
    def __init__(self, root: str | os.PathLike[str] | None = None, *, key: bytes | None = None):
        self.root = _root(root)
        self.key = key if key is not None else encryption_key()
        if len(self.key) != 32:
            raise FarmPolicyError("AES-256-GCM requires a 32-byte key")
        self.artifacts = _child(self.root, "runtime/artifacts")
        self.artifacts.mkdir(parents=True, exist_ok=True)

    def write_json(self, artifact_id: str, data: dict) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", artifact_id or ""):
            raise FarmPolicyError("invalid artifact ID")
        plaintext = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(self.key).encrypt(nonce, plaintext, artifact_id.encode("ascii"))
        envelope = {
            "version": 1, "algorithm": "AES-256-GCM", "artifact_id": artifact_id,
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
            "plaintext_sha256": hashlib.sha256(plaintext).hexdigest(),
            "created_at": _utc_now(),
        }
        destination = _child(self.artifacts, f"{artifact_id}.json")
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)
        return destination

    def read_json(self, artifact_id: str) -> dict:
        path = _child(self.artifacts, f"{artifact_id}.json")
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FarmPolicyError("artifact envelope is unreadable") from exc
        if (not isinstance(envelope, dict) or envelope.get("version") != 1
                or envelope.get("algorithm") != "AES-256-GCM"
                or envelope.get("artifact_id") != artifact_id):
            raise FarmPolicyError("unsupported or mismatched artifact envelope")
        try:
            nonce = base64.b64decode(envelope["nonce_b64"], validate=True)
            ciphertext = base64.b64decode(envelope["ciphertext_b64"], validate=True)
            if len(nonce) != 12 or not ciphertext:
                raise ValueError("invalid authenticated-encryption fields")
            plaintext = AESGCM(self.key).decrypt(nonce, ciphertext, artifact_id.encode("ascii"))
        except (KeyError, TypeError, ValueError) as exc:
            raise FarmPolicyError("artifact envelope has invalid authenticated-encryption fields") from exc
        except Exception as exc:
            # Includes an AES-GCM authentication-tag mismatch. Do not surface
            # crypto-library detail or attacker-controlled envelope content.
            raise FarmPolicyError("artifact authentication failed") from exc
        if hashlib.sha256(plaintext).hexdigest() != envelope.get("plaintext_sha256"):
            raise FarmPolicyError("artifact checksum mismatch")
        try:
            return json.loads(plaintext.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise FarmPolicyError("artifact plaintext is not valid JSON") from exc


def stage_distillation_source(source: str | os.PathLike[str], *, root=None, key: bytes | None = None) -> dict:
    source, raw = _read_allowed_source(source)
    job_id = f"distill_{secrets.token_hex(12)}"
    store = EncryptedArtifactStore(root, key=key)
    artifact_id = f"source_{job_id}"
    store.write_json(artifact_id, {
        "source_name": source.name,
        "raw_text": raw,
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    })
    return {
        "job_id": job_id,
        "workflow": "historical_memory_distillation",
        "artifact_id": artifact_id,
        "privacy_class": "private",
        "idempotency_key": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "created_at": _utc_now(),
    }


def distillation_source_fingerprint(source: str | os.PathLike[str]) -> str:
    """Validate and fingerprint source text without writing an artifact."""
    _path, raw = _read_allowed_source(source)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def distill_review_candidates(envelope: dict, *, root=None, key: bytes | None = None) -> dict:
    if envelope.get("workflow") != "historical_memory_distillation":
        raise FarmPolicyError("this handler only accepts historical memory distillation")
    if envelope.get("workflow") not in ALLOWED_WORKFLOWS:
        raise FarmPolicyError("workflow is not allow-listed")
    job_id = str(envelope.get("job_id", ""))
    if not re.fullmatch(r"distill_[a-f0-9]{24}", job_id):
        raise FarmPolicyError("invalid distillation job ID")
    source = EncryptedArtifactStore(root, key=key).read_json(str(envelope["artifact_id"]))
    source_format, extracted = extract_transcript_text(source.get("source_name", ""), str(source.get("raw_text", "")))
    sanitized = sanitize_text(extracted)
    candidates = []
    for line in sanitized.splitlines():
        line = line.strip()
        if len(line) < 30:
            continue
        lowered = line.lower()
        category = (
            "operator_preference" if any(term in lowered for term in ("prefer", "always", "never")) else
            "hardware_or_runtime_fact" if any(term in lowered for term in ("gpu", "cpu", "ram", "ollama", "windows")) else
            "possible_code_exemplar" if any(term in lowered for term in ("def ", "class ", "test_", "patch")) else None
        )
        if category:
            candidates.append({"category": category, "text": line[:1200], "confidence": "candidate"})
    return {
        "job_id": job_id, "workflow": envelope["workflow"], "status": "review_required",
        "source_sha256": source["source_sha256"], "extracted_text_sha256": hashlib.sha256(extracted.encode("utf-8")).hexdigest(),
        "source_format": source_format, "created_at": _utc_now(),
        "candidates": candidates[:100],
        "promotion_rule": "No candidate may enter active memory or Chroma without operator approval.",
    }
