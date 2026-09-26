#!/usr/bin/env python3
"""Workstation APK review CLI (companion PR 1). Stdlib only.

Reads an APK as a zip. Records SHA-256, signing-cert fingerprint, package id,
and the requested-permission list. Writes one JSONL row. Does not compile,
install, adb, or send anything to the phone.

Fail closed: MANAGE_EXTERNAL_STORAGE, privileged INSTALL_PACKAGES,
BIND_DEVICE_ADMIN / DEVICE_ADMIN, QUERY_ALL_PACKAGES, missing/unparsed
manifest, wrong package id. Flag (not fail) REQUEST_INSTALL_PACKAGES —
allowed on the companion only after PR 6.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_JSONL = HERE / "runtime" / "lxmf" / "apk_review.jsonl"
EXPECTED_PACKAGE = "local.equalshares.sidebandagent"
APK_SIG_MAGIC = b"APK Sig Block 42"
APK_SIG_V2 = 0x7109871A
APK_SIG_V3 = 0xF05368C0

# Binary XML
RES_XML = 0x0003
RES_STRING_POOL = 0x0001
RES_XML_START_ELEMENT = 0x0102
UTF8_FLAG = 1 << 8
TYPE_STRING = 0x03
TYPE_INT_DEC = 0x10
TYPE_INT_HEX = 0x11
TYPE_FIRST_INT = 0x10
TYPE_LAST_INT = 0x1F

FAIL_CLOSED_PERMISSIONS = frozenset({
    "android.permission.MANAGE_EXTERNAL_STORAGE",
    "android.permission.INSTALL_PACKAGES",
    "android.permission.BIND_DEVICE_ADMIN",
    "android.permission.QUERY_ALL_PACKAGES",
})
FAIL_CLOSED_STRINGS = frozenset({
    "android.app.action.DEVICE_ADMIN_ENABLED",
    "android.app.device_admin",
})
FLAG_PERMISSIONS = frozenset({
    "android.permission.REQUEST_INSTALL_PACKAGES",
})

DECISION_ACCEPT = "accept"
DECISION_FLAG = "flag"
DECISION_REJECT = "reject"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def review_apk(path: Path, *, expected_package: str = EXPECTED_PACKAGE) -> dict:
    """Return a JSON-serializable review row. Never includes APK bytes."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    file_sha = sha256_file(path)
    blob = path.read_bytes()
    fail_closed: list[str] = []
    flags: list[str] = []
    package = None
    version_name = None
    version_code = None
    permissions: list[str] = []
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                manifest = zf.read("AndroidManifest.xml")
            except KeyError:
                fail_closed.append("missing_manifest")
                manifest = b""
    except zipfile.BadZipFile:
        fail_closed.append("not_a_zip")
        manifest = b""
    if manifest:
        try:
            parsed = parse_axml(manifest)
            package = parsed.get("package")
            version_name = parsed.get("version_name")
            version_code = parsed.get("version_code")
            permissions = list(parsed.get("permissions") or [])
        except Exception:
            fail_closed.append("manifest_unparsed")
    signing = parse_signing(blob)
    if signing is None:
        fail_closed.append("unsigned")
    for perm in permissions:
        if perm in FAIL_CLOSED_PERMISSIONS:
            fail_closed.append(perm)
        if perm in FLAG_PERMISSIONS:
            flags.append(perm)
    joined = " ".join(permissions)
    for token in FAIL_CLOSED_STRINGS:
        if token in joined:
            fail_closed.append(token)
    if expected_package and package and package != expected_package:
        fail_closed.append("package_id")
    if expected_package and not package and "manifest_unparsed" not in fail_closed \
            and "missing_manifest" not in fail_closed and "not_a_zip" not in fail_closed:
        fail_closed.append("package_id")
    fail_closed = list(dict.fromkeys(fail_closed))
    flags = list(dict.fromkeys(flags))
    if fail_closed:
        decision = DECISION_REJECT
    elif flags:
        decision = DECISION_FLAG
    else:
        decision = DECISION_ACCEPT
    return {
        "at": time.time(),
        "path": str(path),
        "bytes": size,
        "sha256": file_sha,
        "package": package,
        "version_name": version_name,
        "version_code": version_code,
        "permissions": permissions,
        "signing": signing,
        "fail_closed": fail_closed,
        "flags": flags,
        "decision": decision,
        "expected_package": expected_package,
    }


def append_review(row: dict, jsonl_path: Path | None = None) -> Path:
    dest = Path(jsonl_path) if jsonl_path else DEFAULT_JSONL
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return dest


def parse_axml(data: bytes) -> dict:
    """Parse binary AndroidManifest.xml. Raises on garbage."""
    if len(data) < 8:
        raise ValueError("axml too short")
    kind, header_size, total = struct.unpack_from("<HHI", data, 0)
    if kind != RES_XML or total > len(data):
        # Some test/debug zips store textual XML; refuse rather than accept.
        if data.lstrip().startswith(b"<?xml") or data.lstrip().startswith(b"<manifest"):
            raise ValueError("textual AndroidManifest.xml is not accepted")
        raise ValueError(f"not binary XML (type=0x{kind:04x})")
    offset = header_size
    strings: list[str] = []
    permissions: list[str] = []
    package = None
    version_name = None
    version_code = None
    while offset + 8 <= min(total, len(data)):
        ctype, chsize_hdr, csize = struct.unpack_from("<HHI", data, offset)
        if csize < 8 or offset + csize > len(data):
            break
        chunk = data[offset:offset + csize]
        if ctype == RES_STRING_POOL:
            strings = _parse_string_pool(chunk)
        elif ctype == RES_XML_START_ELEMENT:
            name, attrs = _parse_start_element(chunk, strings)
            if name == "manifest":
                package = attrs.get("package") or package
                version_name = attrs.get("versionName") or version_name
                raw_code = attrs.get("versionCode")
                if raw_code is not None:
                    try:
                        version_code = int(raw_code)
                    except (TypeError, ValueError):
                        version_code = raw_code
            elif name in {"uses-permission", "uses-permission-sdk-23"}:
                perm = attrs.get("name")
                if perm:
                    permissions.append(str(perm))
        offset += csize
    return {
        "package": package,
        "version_name": version_name,
        "version_code": version_code,
        "permissions": permissions,
    }


def _parse_string_pool(chunk: bytes) -> list[str]:
    if len(chunk) < 28:
        return []
    _ctype, header_size, _csize, count, _styles, flags, strings_start, _styles_start = (
        struct.unpack_from("<HHIIIIII", chunk, 0))
    utf8 = bool(flags & UTF8_FLAG)
    strings: list[str] = []
    for i in range(count):
        off_pos = header_size + i * 4
        if off_pos + 4 > len(chunk):
            break
        rel, = struct.unpack_from("<I", chunk, off_pos)
        pos = strings_start + rel
        if pos >= len(chunk):
            strings.append("")
            continue
        if utf8:
            pos = _skip_utf8_len(chunk, pos)
            pos = _skip_utf8_len(chunk, pos)
            end = chunk.find(b"\x00", pos)
            if end < 0:
                end = len(chunk)
            strings.append(chunk[pos:end].decode("utf-8", "replace"))
        else:
            if pos + 2 > len(chunk):
                strings.append("")
                continue
            char_count, = struct.unpack_from("<H", chunk, pos)
            pos += 2
            if char_count & 0x8000:
                if pos + 2 > len(chunk):
                    strings.append("")
                    continue
                extra, = struct.unpack_from("<H", chunk, pos)
                char_count = ((char_count & 0x7FFF) << 16) | extra
                pos += 2
            raw = chunk[pos:pos + char_count * 2]
            strings.append(raw.decode("utf-16le", "replace"))
    return strings


def _skip_utf8_len(chunk: bytes, pos: int) -> int:
    if pos >= len(chunk):
        return pos
    first = chunk[pos]
    pos += 1
    if first & 0x80:
        pos += 1
    return pos


def _parse_start_element(chunk: bytes, strings: list[str]) -> tuple[str, dict]:
    # ResXMLTree_node (16 bytes) + ResXMLTree_attrExt (20 bytes)
    if len(chunk) < 36:
        return "", {}
    name_idx, = struct.unpack_from("<i", chunk, 20)
    attr_start, attr_size, attr_count = struct.unpack_from("<HHH", chunk, 24)
    name = _idx(strings, name_idx)
    attrs: dict[str, object] = {}
    base = 16 + attr_start
    for i in range(attr_count):
        pos = base + i * attr_size
        if pos + 20 > len(chunk):
            break
        ns_idx, attr_name_idx, raw_idx, value_size, _res0, data_type, data = (
            struct.unpack_from("<iiiHBBI", chunk, pos))
        del ns_idx, value_size
        key = _idx(strings, attr_name_idx)
        if not key:
            continue
        if data_type == TYPE_STRING:
            attrs[key] = _idx(strings, data)
        elif TYPE_FIRST_INT <= data_type <= TYPE_LAST_INT:
            attrs[key] = data
        else:
            raw = _idx(strings, raw_idx) if raw_idx >= 0 else None
            attrs[key] = raw if raw else data
    return name, attrs


def _idx(strings: list[str], index: int) -> str:
    if index < 0 or index >= len(strings):
        return ""
    return strings[index]


def parse_signing(apk_bytes: bytes) -> dict | None:
    """APK Signature Scheme v2/v3 first certificate, if present."""
    block = _apk_signing_block(apk_bytes)
    if not block:
        return None
    pairs = _signing_pairs(block)
    scheme = None
    value = None
    if APK_SIG_V2 in pairs:
        scheme = "v2"
        value = pairs[APK_SIG_V2]
    elif APK_SIG_V3 in pairs:
        scheme = "v3"
        value = pairs[APK_SIG_V3]
    if value is None:
        return None
    certs = _v2_certificates(value)
    if not certs:
        return {"scheme": scheme, "cert_sha256": None, "subject": None}
    der = certs[0]
    return {
        "scheme": scheme,
        "cert_sha256": hashlib.sha256(der).hexdigest(),
        "subject": _der_cn(der),
    }


def _apk_signing_block(data: bytes) -> bytes | None:
    eocd = data.rfind(b"PK\x05\x06")
    if eocd < 0 or eocd + 22 > len(data):
        return None
    cd_offset, = struct.unpack_from("<I", data, eocd + 16)
    if cd_offset < 32 or cd_offset > len(data):
        return None
    # magic immediately precedes the central directory
    magic_at = cd_offset - 16
    if magic_at < 0 or data[magic_at:cd_offset] != APK_SIG_MAGIC:
        return None
    size2, = struct.unpack_from("<Q", data, magic_at - 8)
    block_start = cd_offset - 32 - (size2 - 24)
    # size2 covers from after the first size field through magic inclusive:
    # pairs + trailing size + magic = size2, so start = cd - 16 - 8 - (size2 - 24) wait.
    # Layout: [u64 size][pairs][u64 size][16 magic]
    # size = len(pairs) + 8 + 16 = len(pairs) + 24
    # total block = 8 + size = len(pairs) + 32
    # cd_offset - total_block = start of first u64
    total_block = size2 + 8
    start = cd_offset - total_block
    if start < 0:
        return None
    size1, = struct.unpack_from("<Q", data, start)
    if size1 != size2:
        return None
    return data[start + 8:magic_at - 8]


def _signing_pairs(pairs_blob: bytes) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    off = 0
    while off + 12 <= len(pairs_blob):
        length, = struct.unpack_from("<Q", pairs_blob, off)
        off += 8
        if length < 4 or off + length > len(pairs_blob):
            break
        pair_id, = struct.unpack_from("<I", pairs_blob, off)
        out[pair_id] = pairs_blob[off + 4:off + length]
        off += length
    return out


def _v2_certificates(value: bytes) -> list[bytes]:
    """Length-prefixed signers → first signer's certificate list."""
    if len(value) < 4:
        return []
    signers_len, = struct.unpack_from("<I", value, 0)
    off = 4
    end = min(4 + signers_len, len(value))
    certs: list[bytes] = []
    while off + 4 <= end:
        slen, = struct.unpack_from("<I", value, off)
        off += 4
        signer = value[off:off + slen]
        off += slen
        certs.extend(_certs_from_signer(signer))
        if certs:
            break
    return certs


def _certs_from_signer(signer: bytes) -> list[bytes]:
    if len(signer) < 4:
        return []
    sd_len, = struct.unpack_from("<I", signer, 0)
    sd = signer[4:4 + sd_len]
    if len(sd) < 4:
        return []
    digests_len, = struct.unpack_from("<I", sd, 0)
    p = 4 + digests_len
    if p + 4 > len(sd):
        return []
    certs_len, = struct.unpack_from("<I", sd, p)
    p += 4
    cend = p + certs_len
    out: list[bytes] = []
    while p + 4 <= cend and p + 4 <= len(sd):
        clen, = struct.unpack_from("<I", sd, p)
        p += 4
        out.append(sd[p:p + clen])
        p += clen
    return out


def _der_cn(der: bytes) -> str | None:
    """Best-effort CN from X.509 DER without a crypto library."""
    needle = b"\x06\x03\x55\x04\x03"
    start = 0
    while True:
        idx = der.find(needle, start)
        if idx < 0:
            return None
        i = idx + len(needle)
        if i + 2 > len(der):
            return None
        tag = der[i]
        i += 1
        length = der[i]
        i += 1
        if length & 0x80:
            n = length & 0x7F
            if i + n > len(der):
                start = idx + 1
                continue
            length = int.from_bytes(der[i:i + n], "big")
            i += n
        if i + length > len(der):
            start = idx + 1
            continue
        if tag in (0x0C, 0x13, 0x16, 0x1B, 0x14):
            try:
                return der[i:i + length].decode("utf-8")
            except UnicodeDecodeError:
                return der[i:i + length].decode("latin-1")
        start = idx + 1


def _print_row(row: dict) -> None:
    print(f"path      : {row['path']}")
    print(f"bytes     : {row['bytes']}")
    print(f"sha256    : {row['sha256']}")
    print(f"package   : {row.get('package')}")
    print(f"version   : {row.get('version_name')} ({row.get('version_code')})")
    signing = row.get("signing") or {}
    print(f"signing   : {signing.get('scheme')} cert={signing.get('cert_sha256')} "
          f"subject={signing.get('subject')}")
    print(f"perms     : {', '.join(row.get('permissions') or []) or '(none)'}")
    print(f"fail      : {', '.join(row.get('fail_closed') or []) or '(none)'}")
    print(f"flags     : {', '.join(row.get('flags') or []) or '(none)'}")
    print(f"decision  : {row['decision']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review an APK (hash, cert, permissions). Does not install.")
    parser.add_argument("apk", type=Path)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL,
                        help="append review row (default: runtime/lxmf/apk_review.jsonl)")
    parser.add_argument("--expected-package", default=EXPECTED_PACKAGE)
    parser.add_argument("--no-jsonl", action="store_true")
    args = parser.parse_args(argv)
    row = review_apk(args.apk, expected_package=args.expected_package)
    if not args.no_jsonl:
        dest = append_review(row, args.jsonl)
        print(f"jsonl     : {dest}")
    _print_row(row)
    if row["decision"] == DECISION_REJECT:
        return 1
    if row["decision"] == DECISION_FLAG:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
