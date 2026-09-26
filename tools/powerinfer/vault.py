"""Encrypted PowerInfer model vault outside the git tree.

Creates the per-build layout, refuses overwrites, never deletes evidence,
hashes sources then marks them read-only, and stores private calibration or
result payloads as AES-256-GCM envelopes. No GPU work on import.
"""
from __future__ import annotations

import base64
import ctypes
import json
import os
import shutil
import stat
from pathlib import Path
from typing import Any

from pipeline_lib import (
    REPO_ROOT,
    sha256_file,
    sha256_tree,
    target_config,
    utc_now,
    write_json,
)

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    _CRYPTOGRAPHY_AVAILABLE = True
    _CRYPTOGRAPHY_REASON = ""
except ImportError:
    AESGCM = None  # type: ignore[assignment,misc]
    _CRYPTOGRAPHY_AVAILABLE = False
    _CRYPTOGRAPHY_REASON = "cryptography is not installed (pip install cryptography)"

ROOT_DIRS = ("production", "quarantine", "scratch", "private", "keys")
BUNDLE_DIRS = (
    "source",
    "calibration",
    "activation",
    "predictor",
    "output",
    "validation",
    "runtime",
)
SAFETY_MARGIN = 0.20
FILE_ATTRIBUTE_READONLY = 0x1
PREFERRED_VAULT = Path(r"D:\PowerInferModels")
FALLBACK_VAULT = REPO_ROOT / "artifacts" / "powerinfer_vault"


class VaultError(RuntimeError):
    """Operator-facing vault policy failure."""


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _dpapi_protect(data: bytes) -> bytes:
    if os.name != "nt":
        raise VaultError("Windows DPAPI is required to persist a vault key without POWERINFER_VAULT_KEY")
    source = ctypes.create_string_buffer(data, len(data))
    inp = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    out = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_wchar_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = ctypes.c_int
    if not crypt32.CryptProtectData(
        ctypes.byref(inp), "PowerInfer vault key", None, None, None, 0x1, ctypes.byref(out)
    ):
        raise OSError(ctypes.get_last_error(), "DPAPI protection failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _dpapi_unprotect(data: bytes) -> bytes:
    if os.name != "nt":
        raise VaultError("Windows DPAPI is required to read a persisted vault key")
    source = ctypes.create_string_buffer(data, len(data))
    inp = _DataBlob(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_char)))
    out = _DataBlob()
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = ctypes.c_int
    if not crypt32.CryptUnprotectData(
        ctypes.byref(inp), None, None, None, None, 0x1, ctypes.byref(out)
    ):
        raise OSError(ctypes.get_last_error(), "DPAPI unprotection failed")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def default_vault_path() -> Path:
    env = os.environ.get("POWERINFER_VAULT")
    if env:
        return Path(env)
    if PREFERRED_VAULT.exists() or PREFERRED_VAULT.parent.exists():
        return PREFERRED_VAULT
    return FALLBACK_VAULT


def assert_outside_repo(path: Path, *, allow_in_repo: bool = False) -> None:
    resolved = path.resolve()
    repo = REPO_ROOT.resolve()
    try:
        resolved.relative_to(repo)
    except ValueError:
        return
    if allow_in_repo:
        return
    raise VaultError(
        f"vault path {resolved} is inside the git repository {repo}. "
        "Use D:\\PowerInferModels or set POWERINFER_VAULT to a path outside the tree."
    )


def log_access(vault: Path, action: str, **fields: Any) -> None:
    line = {"ts": utc_now(), "action": action, **fields}
    path = vault / "access.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def refuse_delete(path: Path) -> None:
    """Evidence is retained. Callers must not rmtree conversion artifacts."""
    raise VaultError(
        f"refusing to delete {path}; conversion evidence is retained. "
        "Quarantine by status in manifest.json instead of removing files."
    )


def disk_status(path: Path) -> dict[str, int]:
    path.mkdir(parents=True, exist_ok=True)
    usage = shutil.disk_usage(path)
    return {"total": usage.total, "used": usage.used, "free": usage.free}


def estimate_bundle_bytes(model_id: str, *, source_bytes: int = 0) -> dict[str, int]:
    cfg = target_config(model_id)
    samples = int(cfg["max_samples"])
    layers = int(cfg["num_hidden_layers"])
    hidden = int(cfg["hidden_size"])
    intermediate = int(cfg["intermediate_size"])
    predictor_mmaps = samples * (hidden + intermediate) * 2 * layers
    activations = layers * intermediate * 4
    gguf_f16 = int((hidden * intermediate * 3 + hidden * hidden * 4) * layers * 2)
    need = source_bytes + predictor_mmaps + activations + gguf_f16 + 2 * 1024**3
    return {
        "source_bytes": source_bytes,
        "predictor_mmaps": predictor_mmaps,
        "activations": activations,
        "gguf_f16_estimate": gguf_f16,
        "need_bytes": need,
        "need_with_margin": int(need * (1 + SAFETY_MARGIN)),
    }


def preflight(vault: Path, *, need_bytes: int) -> dict[str, Any]:
    status = disk_status(vault)
    required = int(need_bytes * (1 + SAFETY_MARGIN)) if need_bytes else 0
    ok = status["free"] >= required
    report = {
        "vault": str(vault),
        "free_bytes": status["free"],
        "need_bytes": need_bytes,
        "required_with_margin": required,
        "safety_margin": SAFETY_MARGIN,
        "ok": ok,
    }
    if not ok:
        raise VaultError(
            f"free disk {status['free']} bytes is below required {required} "
            f"(need {need_bytes} plus {int(SAFETY_MARGIN * 100)}% margin) at {vault}"
        )
    return report


def _gitignore(vault: Path) -> None:
    """Create the vault ignore file once without rewriting user-owned state.

    Vault initialisation is deliberately performed before every execute stage.
    An existing file is evidence/configuration, so treating it as immutable
    avoids a needless write and works when a backup/indexer holds the file.
    """
    path = vault / ".gitignore"
    if path.exists():
        return
    path.write_text(
        "\n".join(
            [
                "keys/",
                "private/",
                "scratch/",
                "*.gguf",
                "*.mmap",
                "*.pt",
                "access.log",
                "",
            ]
        ),
        encoding="utf-8",
    )


def init_vault(vault: Path, *, allow_in_repo: bool = False) -> dict[str, Any]:
    assert_outside_repo(vault, allow_in_repo=allow_in_repo)
    vault.mkdir(parents=True, exist_ok=True)
    for name in ROOT_DIRS:
        (vault / name).mkdir(exist_ok=True)
    _gitignore(vault)
    metadata_path = vault / "vault.json"
    # Initialisation runs before every execute stage. Once the vault manifest
    # exists, it is evidence/configuration and must not be rewritten merely to
    # refresh a timestamp. This also keeps a temporary Windows file lock from
    # blocking a safe read-only reuse of the established vault.
    if metadata_path.exists():
        with metadata_path.open("r", encoding="utf-8") as handle:
            existing = json.load(handle)
        if not isinstance(existing, dict):
            raise VaultError(f"vault metadata is not an object: {metadata_path}")
        return existing
    meta = {
        "created_at": utc_now(),
        "vault": str(vault.resolve()),
        "encryption": "AES-256-GCM",
        "key_storage": "DPAPI vault/keys/vault_key.dpapi or POWERINFER_VAULT_KEY",
        "auto_delete": False,
        "layout": {
            "production": "accepted GGUF bundles only",
            "quarantine": "failed or rejected builds; files retained",
            "scratch": "runtime GPU indexes and caches; never auto-deleted",
            "private": "AES-256-GCM envelopes for private calibration/results",
            "keys": "DPAPI-wrapped 32-byte key; never commit",
        },
    }
    write_json(metadata_path, meta)
    log_access(vault, "init", path=str(vault.resolve()))
    return meta


def bundle_paths(vault: Path, model_id: str, build_id: str) -> dict[str, Path]:
    root = vault / model_id / build_id
    paths = {"root": root}
    for name in BUNDLE_DIRS:
        paths[name] = root / name
    paths["manifest"] = root / "manifest.json"
    return paths


def create_bundle(vault: Path, model_id: str, build_id: str, *, force: bool = False) -> dict[str, Path]:
    paths = bundle_paths(vault, model_id, build_id)
    root = paths["root"]
    if root.exists() and any(root.iterdir()) and not force:
        raise VaultError(f"refusing to overwrite existing bundle {root}")
    for name in BUNDLE_DIRS:
        paths[name].mkdir(parents=True, exist_ok=True)
    log_access(vault, "create_bundle", model_id=model_id, build_id=build_id, path=str(root))
    return paths


def _set_readonly(path: Path) -> None:
    if os.name == "nt":
        attrs = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attrs != -1:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attrs | FILE_ATTRIBUTE_READONLY)
    mode = path.stat().st_mode
    path.chmod(mode & ~stat.S_IWRITE)


def protect_source(source_dir: Path, vault: Path | None = None) -> dict[str, Any]:
    if not source_dir.is_dir():
        raise VaultError(f"source directory missing: {source_dir}")
    tree = sha256_tree(source_dir)
    locked = []
    for path in source_dir.rglob("*"):
        if path.is_file():
            _set_readonly(path)
            locked.append(path.relative_to(source_dir).as_posix())
    stamp = {
        "locked_at": utc_now(),
        "source": str(source_dir),
        "files_locked": len(locked),
        "tree": tree,
        "policy": "read-only after hash; do not edit shards in place",
    }
    write_json(source_dir / "SOURCE_LOCKED.json", stamp)
    if vault:
        log_access(
            vault,
            "protect_source",
            path=str(source_dir),
            combined_sha256=tree.get("combined_sha256"),
            files=tree.get("count"),
        )
    return stamp


def load_key(vault: Path) -> bytes:
    supplied = os.environ.get("POWERINFER_VAULT_KEY", "").strip()
    if supplied:
        value = base64.urlsafe_b64decode(supplied + "=" * (-len(supplied) % 4))
        if len(value) != 32:
            raise VaultError("POWERINFER_VAULT_KEY must decode to exactly 32 bytes")
        return value
    key_file = vault / "keys" / "vault_key.dpapi"
    if key_file.is_file():
        value = _dpapi_unprotect(key_file.read_bytes())
        if len(value) != 32:
            raise VaultError("stored vault key has an invalid length")
        return value
    value = os.urandom(32)
    _atomic_write_bytes(key_file, _dpapi_protect(value))
    log_access(vault, "create_key", path=str(key_file))
    return value


def encrypt_private(vault: Path, source: Path, *, label: str) -> dict[str, Any]:
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise VaultError(_CRYPTOGRAPHY_REASON)
    if not source.is_file():
        raise VaultError(f"missing plaintext {source}")
    digest = sha256_file(source)
    nonce = os.urandom(12)
    aad = label.encode("utf-8")
    cipher = AESGCM(load_key(vault)).encrypt(nonce, source.read_bytes(), aad)
    dest = vault / "private" / f"{label}.envelope.json"
    if dest.exists():
        raise VaultError(f"refusing to overwrite envelope {dest}")
    envelope = {
        "version": 1,
        "algorithm": "AES-256-GCM",
        "label": label,
        "source_name": source.name,
        "plaintext_sha256": digest,
        "plaintext_bytes": source.stat().st_size,
        "created_at": utc_now(),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(cipher).decode("ascii"),
        "aad": label,
    }
    write_json(dest, envelope)
    log_access(
        vault,
        "encrypt_private",
        label=label,
        envelope=str(dest),
        plaintext_sha256=digest,
        plaintext_bytes=envelope["plaintext_bytes"],
    )
    return {
        "envelope": str(dest),
        "plaintext_sha256": digest,
        "algorithm": "AES-256-GCM",
        "deleted_plaintext": False,
    }


def decrypt_private(vault: Path, envelope_path: Path, dest: Path) -> dict[str, Any]:
    if not _CRYPTOGRAPHY_AVAILABLE:
        raise VaultError(_CRYPTOGRAPHY_REASON)
    if dest.exists():
        raise VaultError(f"refusing to overwrite {dest}")
    envelope = json.loads(envelope_path.read_text(encoding="utf-8"))
    if envelope.get("algorithm") != "AES-256-GCM":
        raise VaultError("envelope is not AES-256-GCM")
    nonce = base64.b64decode(envelope["nonce"])
    cipher = base64.b64decode(envelope["ciphertext"])
    aad = str(envelope.get("aad") or envelope.get("label") or "").encode("utf-8")
    plain = AESGCM(load_key(vault)).decrypt(nonce, cipher, aad)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(plain)
    actual = sha256_file(dest)
    if actual != envelope.get("plaintext_sha256"):
        raise VaultError("decrypted digest does not match envelope plaintext_sha256")
    log_access(
        vault,
        "decrypt_private",
        envelope=str(envelope_path),
        dest=str(dest),
        plaintext_sha256=actual,
    )
    return {"dest": str(dest), "sha256": actual, "bytes": len(plain)}
