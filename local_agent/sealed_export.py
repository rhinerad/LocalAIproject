#!/usr/bin/env python3
"""Synthetic-only age sealer for a future historical-chat export.

v1 encrypts the benign distill ``--sample`` fixture to an age X25519
recipient. It does not read ``local_agent/chats/``, does not run
``submit_distillation`` without ``--sample``, and does not write plaintext
to disk. Decrypt is not a CLI command on this workstation.

See ``docs/design_notes/SEALED_CHAT_EXPORT_2026-09-05.md``.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import sys
from pathlib import Path

from atomic_io import atomic_write_bytes

HERE = Path(__file__).resolve().parent
CHAT_ROOT = HERE / "chats"
# Identical to worker_farm.submit_distillation.SAMPLE. Tests lock the copy.
SYNTHETIC_FIXTURE = (
    "Preference: keep the GPU available for interactive work.\n"
    "Hardware: the workstation has an RTX GPU and CPU fallback.\n"
    "def example(): return 'review this candidate before promotion'\n"
)
_BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
_STREAM_CHUNK = 64 * 1024
_MAX_PLAINTEXT = 25 * 1024 * 1024


class SealedExportError(ValueError):
    pass


def assert_not_chat_source(path: Path | str) -> None:
    """Refuse any path under ``local_agent/chats/`` before a read can happen."""
    raw = Path(path)
    candidates = [raw]
    if not raw.is_absolute():
        candidates.append(HERE / raw)
        candidates.append(Path.cwd() / raw)
    chat_root = CHAT_ROOT.resolve()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = candidate
        if resolved == chat_root or chat_root in resolved.parents:
            raise SealedExportError("refused: path is under local_agent/chats/")
        parts = [str(part).lower() for part in resolved.parts]
        if "local_agent" in parts:
            index = parts.index("local_agent")
            if index + 1 < len(parts) and parts[index + 1] == "chats":
                raise SealedExportError("refused: path is under local_agent/chats/")


def _bech32_polymod(values: list[int]) -> int:
    generators = (0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3)
    checksum = 1
    for value in values:
        top = checksum >> 25
        checksum = ((checksum & 0x1FFFFFF) << 5) ^ value
        for i, gen in enumerate(generators):
            if (top >> i) & 1:
                checksum ^= gen
    return checksum


def _bech32_hrp_expand(hrp: str) -> list[int]:
    return [ord(char) >> 5 for char in hrp] + [0] + [ord(char) & 31 for char in hrp]


def _convertbits(data: bytes | list[int], from_bits: int, to_bits: int, *, pad: bool) -> list[int]:
    accumulator = 0
    bits = 0
    out: list[int] = []
    max_value = (1 << to_bits) - 1
    for value in data:
        accumulator = (accumulator << from_bits) | int(value)
        bits += from_bits
        while bits >= to_bits:
            bits -= to_bits
            out.append((accumulator >> bits) & max_value)
    if pad and bits:
        out.append((accumulator << (to_bits - bits)) & max_value)
    return out


def _bech32_encode(hrp: str, data: bytes) -> str:
    converted = _convertbits(data, 8, 5, pad=True)
    checksum = _bech32_polymod(_bech32_hrp_expand(hrp) + converted + [0] * 6) ^ 1
    checksum_values = [(checksum >> 5 * (5 - i)) & 31 for i in range(6)]
    return hrp + "1" + "".join(_BECH32_CHARSET[i] for i in converted + checksum_values)


def _bech32_decode(value: str) -> tuple[str, bytes]:
    raw = str(value or "").strip()
    lowered = raw.lower()
    if "1" not in lowered:
        raise SealedExportError("invalid age recipient")
    hrp, _, data = lowered.rpartition("1")
    if not hrp or not data:
        raise SealedExportError("invalid age recipient")
    try:
        decoded = [_BECH32_CHARSET.index(char) for char in data]
    except ValueError as exc:
        raise SealedExportError("invalid age recipient") from exc
    if _bech32_polymod(_bech32_hrp_expand(hrp) + decoded) != 1:
        raise SealedExportError("invalid age recipient checksum")
    payload = _convertbits(decoded[:-6], 5, 8, pad=False)
    return hrp, bytes(payload)


def decode_recipient(recipient: str) -> bytes:
    hrp, data = _bech32_decode(recipient)
    if hrp != "age" or len(data) != 32:
        raise SealedExportError("recipient must be an age X25519 public key")
    return data


def encode_recipient(public: bytes) -> str:
    if len(public) != 32:
        raise SealedExportError("age public key must be 32 bytes")
    return _bech32_encode("age", public)


def encode_identity(secret: bytes) -> str:
    if len(secret) != 32:
        raise SealedExportError("age identity must be 32 bytes")
    return _bech32_encode("age-secret-key-", secret).upper()


def decode_identity(identity: str) -> bytes:
    hrp, data = _bech32_decode(identity)
    if hrp != "age-secret-key-" or len(data) != 32:
        raise SealedExportError("identity must be an AGE-SECRET-KEY-1 key")
    return data


def generate_identity() -> tuple[str, str]:
    """Return ``(AGE-SECRET-KEY-…, age1…)``. Tests only; not a workstation CLI."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )

    private = X25519PrivateKey.generate()
    secret = private.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return encode_identity(secret), encode_recipient(public)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii").rstrip("=")


def _b64d(text: str) -> bytes:
    pad = "=" * ((4 - len(text) % 4) % 4)
    return base64.b64decode(text + pad)


def _hkdf(ikm: bytes, *, salt: bytes, info: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(ikm)


def _x25519_stanza(file_key: bytes, recipient_public: bytes) -> bytes:
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    ephemeral = X25519PrivateKey.generate()
    share = ephemeral.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    shared = ephemeral.exchange(X25519PublicKey.from_public_bytes(recipient_public))
    wrap_key = _hkdf(shared, salt=share + recipient_public, info=b"age-encryption.org/v1/X25519")
    wrapped = ChaCha20Poly1305(wrap_key).encrypt(b"\x00" * 12, file_key, None)
    return (
        b"-> X25519 " + _b64(share).encode("ascii") + b"\n"
        + _b64(wrapped).encode("ascii") + b"\n"
    )


def _stream_encrypt(file_key: bytes, plaintext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    payload_key = _hkdf(file_key, salt=b"", info=b"payload")
    aead = ChaCha20Poly1305(payload_key)
    if not plaintext:
        return aead.encrypt(b"\x00" * 11 + b"\x01", b"", None)
    chunks: list[bytes] = []
    offset = 0
    counter = 0
    while offset < len(plaintext):
        piece = plaintext[offset:offset + _STREAM_CHUNK]
        offset += len(piece)
        last = offset >= len(plaintext)
        nonce = counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")
        chunks.append(aead.encrypt(nonce, piece, None))
        counter += 1
    return b"".join(chunks)


def _stream_decrypt(file_key: bytes, ciphertext: bytes) -> bytes:
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

    payload_key = _hkdf(file_key, salt=b"", info=b"payload")
    aead = ChaCha20Poly1305(payload_key)
    if not ciphertext:
        raise SealedExportError("age payload is empty")
    out = bytearray()
    offset = 0
    counter = 0
    chunk_with_tag = _STREAM_CHUNK + 16
    while True:
        remaining = len(ciphertext) - offset
        if remaining <= 0:
            raise SealedExportError("age payload truncated")
        last = remaining <= chunk_with_tag
        size = remaining if last else chunk_with_tag
        nonce = counter.to_bytes(11, "big") + (b"\x01" if last else b"\x00")
        out.extend(aead.decrypt(nonce, ciphertext[offset:offset + size], None))
        offset += size
        counter += 1
        if last:
            return bytes(out)


def encrypt_age(plaintext: bytes, recipients: list[str]) -> bytes:
    if not recipients:
        raise SealedExportError("at least one age recipient is required")
    if len(plaintext) > _MAX_PLAINTEXT:
        raise SealedExportError("plaintext exceeds the 25 MiB seal cap")
    file_key = os.urandom(16)
    stanzas = [_x25519_stanza(file_key, decode_recipient(item)) for item in recipients]
    header_without_mac = b"age-encryption.org/v1\n" + b"".join(stanzas) + b"---"
    mac_key = _hkdf(file_key, salt=b"", info=b"header")
    mac = hmac.new(mac_key, header_without_mac, hashlib.sha256).digest()
    header = header_without_mac + b" " + _b64(mac).encode("ascii") + b"\n"
    return header + _stream_encrypt(file_key, plaintext)


def decrypt_age_for_tests(ciphertext: bytes, identity: str) -> bytes:
    """Round-trip helper for tests. Not exposed as a workstation CLI."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey,
    )
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    try:
        header, payload = ciphertext.split(b"\n--- ", 1)
    except ValueError as exc:
        raise SealedExportError("age header is missing") from exc
    mac_b64, _, payload = payload.partition(b"\n")
    header_without_mac = header + b"\n---"
    secret = decode_identity(identity)
    private = X25519PrivateKey.from_private_bytes(secret)
    our_pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    file_key = None
    lines = header.split(b"\n")
    if lines[:1] != [b"age-encryption.org/v1"]:
        raise SealedExportError("unsupported age version")
    i = 1
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line.startswith(b"-> X25519 "):
            continue
        share = _b64d(line.split()[-1].decode("ascii"))
        body = lines[i]
        i += 1
        wrapped = _b64d(body.decode("ascii"))
        shared = private.exchange(X25519PublicKey.from_public_bytes(share))
        wrap_key = _hkdf(shared, salt=share + our_pub, info=b"age-encryption.org/v1/X25519")
        try:
            file_key = ChaCha20Poly1305(wrap_key).decrypt(b"\x00" * 12, wrapped, None)
        except Exception:
            continue
    if file_key is None:
        raise SealedExportError("age identity does not match any recipient")
    mac_key = _hkdf(file_key, salt=b"", info=b"header")
    expected = hmac.new(mac_key, header_without_mac, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64d(mac_b64.decode("ascii"))):
        raise SealedExportError("age header MAC mismatch")
    return _stream_decrypt(file_key, payload)


def load_recipients(text: str) -> list[str]:
    recipients: list[str] = []
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        decode_recipient(stripped)
        recipients.append(stripped)
    if not recipients:
        raise SealedExportError("recipient list is empty")
    return recipients


def seal_from_path(path: Path | str, *, recipient: str, dest_dir: Path) -> Path:
    """Path entry point exists so ``chats/`` refusal can fire before any read.

    v1 never seals a caller-supplied file, even after the path check.
    """
    assert_not_chat_source(path)
    raise SealedExportError(
        "v1 seals only the synthetic distill fixture; real export is not authorized"
    )


def seal_synthetic(*, recipient: str, dest_dir: Path | str) -> dict:
    """Encrypt the distill --sample fixture to *recipient*. Ciphertext file only."""
    dest = Path(dest_dir)
    assert_not_chat_source(dest)
    dest.mkdir(parents=True, exist_ok=True)
    decode_recipient(recipient)
    plaintext = SYNTHETIC_FIXTURE.encode("utf-8")
    ciphertext = encrypt_age(plaintext, [recipient])
    name = f"sealed_export_{secrets.token_hex(6)}.age"
    path = dest / name
    assert_not_chat_source(path)
    atomic_write_bytes(path, ciphertext)
    return {
        "path": str(path),
        "filename": name,
        "ciphertext_sha256": hashlib.sha256(ciphertext).hexdigest(),
        "ciphertext_bytes": len(ciphertext),
        "recipient_sha256": hashlib.sha256(recipient.encode("ascii")).hexdigest(),
        "schema": "sealed-export-v1-synthetic",
    }


_NAME_RE = re.compile(r"^sealed_export_[0-9a-f]{12}\.age$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seal the synthetic distill fixture to an age recipient. "
                    "Does not export real chats.")
    parser.add_argument("--recipient", help="age1… public key")
    parser.add_argument("--recipient-file", type=Path, help="file of age1… lines")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="refused in v1; chats/ is a hard error")
    args = parser.parse_args(argv)
    try:
        if args.source is not None:
            seal_from_path(args.source, recipient=args.recipient or "unused",
                           dest_dir=args.out_dir)
        if bool(args.recipient) == bool(args.recipient_file):
            raise SealedExportError("provide exactly one of --recipient or --recipient-file")
        if args.recipient_file is not None:
            assert_not_chat_source(args.recipient_file)
            recipients = load_recipients(args.recipient_file.read_text(encoding="utf-8"))
            recipient = recipients[0]
        else:
            recipient = args.recipient
        record = seal_synthetic(recipient=recipient, dest_dir=args.out_dir)
        print(record["path"])
        return 0
    except SealedExportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
