#!/usr/bin/env python3
"""Tests for the workstation APK review CLI. No SDK, no compile, no adb."""
from __future__ import annotations

import ast
import hashlib
import io
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import apk_review

EXPECTED = apk_review.EXPECTED_PACKAGE


def _u16(n: int) -> bytes:
    return struct.pack("<H", n)


def _u32(n: int) -> bytes:
    return struct.pack("<I", n)


def _i32(n: int) -> bytes:
    return struct.pack("<i", n)


def _encode_string_pool(strings: list[str]) -> bytes:
    body = b""
    offsets: list[int] = []
    for text in strings:
        offsets.append(len(body))
        piece = _u16(len(text)) + text.encode("utf-16le") + b"\x00\x00"
        if len(piece) % 4:
            piece += b"\x00" * (4 - len(piece) % 4)
        body += piece
    header_size = 28
    offsets_b = b"".join(_u32(o) for o in offsets)
    strings_start = header_size + len(offsets_b)
    size = strings_start + len(body)
    return (struct.pack("<HHIIIIII", 0x0001, header_size, size,
                        len(strings), 0, 0, strings_start, 0)
            + offsets_b + body)


def _start_ns(prefix: int, uri: int) -> bytes:
    return struct.pack("<HHIIIii", 0x0100, 16, 24, 1, 0xFFFFFFFF, prefix, uri)


def _end_ns(prefix: int, uri: int) -> bytes:
    return struct.pack("<HHIIIii", 0x0101, 16, 24, 1, 0xFFFFFFFF, prefix, uri)


def _attr(ns: int, name: int, data_type: int, data: int, raw: int = -1) -> bytes:
    return struct.pack("<iiiHBBI", ns, name, raw, 8, 0, data_type, data)


def _start_el(ns: int, name: int, attrs: bytes) -> bytes:
    count = len(attrs) // 20
    attr_ext = struct.pack("<iiHHHHHH", ns, name, 20, 20, count, 0, 0, 0)
    node = struct.pack("<HHIIi", 0x0102, 16, 16 + 20 + len(attrs), 1, -1)
    return node + attr_ext + attrs


def _end_el(ns: int, name: int) -> bytes:
    return struct.pack("<HHIIIii", 0x0103, 16, 24, 1, 0xFFFFFFFF, ns, name)


def encode_manifest(package: str, permissions: list[str],
                    version_name: str = "1.0", version_code: int = 1) -> bytes:
    android = "android"
    uri = "http://schemas.android.com/apk/res/android"
    strings = [
        android, uri, "manifest", "package", "versionName", "versionCode",
        "uses-permission", "name", package, version_name, *permissions,
    ]
    idx = {s: i for i, s in enumerate(strings)}
    pool = _encode_string_pool(strings)
    resmap = struct.pack("<HHI", 0x0180, 8, 8 + 4) + _u32(0x01010003)
    ns = _start_ns(idx[android], idx[uri])
    man_attrs = (
        _attr(-1, idx["package"], apk_review.TYPE_STRING, idx[package])
        + _attr(-1, idx["versionName"], apk_review.TYPE_STRING, idx[version_name])
        + _attr(-1, idx["versionCode"], apk_review.TYPE_INT_DEC, version_code)
    )
    man_start = _start_el(-1, idx["manifest"], man_attrs)
    body = b""
    for perm in permissions:
        attr = _attr(idx[android], idx["name"], apk_review.TYPE_STRING, idx[perm])
        body += _start_el(-1, idx["uses-permission"], attr)
        body += _end_el(-1, idx["uses-permission"])
    man_end = _end_el(-1, idx["manifest"])
    ns_end = _end_ns(idx[android], idx[uri])
    inner = pool + resmap + ns + man_start + body + man_end + ns_end
    header = struct.pack("<HHI", 0x0003, 8, 8 + len(inner))
    return header + inner


def make_apk(package: str, permissions: list[str], *,
             extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("AndroidManifest.xml", encode_manifest(package, permissions))
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def fake_cert_der(cn: str = "TestCert") -> bytes:
    cn_bytes = cn.encode("utf-8")
    # SEQUENCE { OID CN, UTF8String }
    inner = b"\x06\x03\x55\x04\x03\x0c" + bytes([len(cn_bytes)]) + cn_bytes
    return b"\x30" + bytes([len(inner)]) + inner


def build_v2_value(cert: bytes) -> bytes:
    certs = _u32(len(cert)) + cert
    signed = _u32(0) + _u32(len(certs)) + certs + _u32(0)
    signer_body = _u32(len(signed)) + signed + _u32(0) + _u32(0)
    signer = _u32(len(signer_body)) + signer_body
    return _u32(len(signer)) + signer


def insert_v2_block(apk: bytes, cert: bytes) -> bytes:
    eocd = apk.rfind(b"PK\x05\x06")
    cd_offset, = struct.unpack_from("<I", apk, eocd + 16)
    value = build_v2_value(cert)
    pair = struct.pack("<QI", 4 + len(value), apk_review.APK_SIG_V2) + value
    size = len(pair) + 24
    block = (struct.pack("<Q", size) + pair + struct.pack("<Q", size)
             + apk_review.APK_SIG_MAGIC)
    new_cd = cd_offset + len(block)
    return (apk[:cd_offset] + block + apk[cd_offset:eocd + 16]
            + struct.pack("<I", new_cd) + apk[eocd + 20:])


class ApkReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write(self, name: str, data: bytes) -> Path:
        path = self.dir / name
        path.write_bytes(data)
        return path

    def test_module_does_not_import_agent(self) -> None:
        tree = ast.parse((HERE / "apk_review.py").read_text(encoding="utf8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        for banned in ("agent", "tools", "lxmf_agent", "router", "adb"):
            self.assertNotIn(banned, names)

    def test_clean_companion_apk_accepts(self) -> None:
        data = make_apk(EXPECTED, ["android.permission.CAMERA"])
        path = self._write("clean.apk", data)
        row = apk_review.review_apk(path)
        self.assertEqual(apk_review.DECISION_REJECT, row["decision"])
        self.assertIn("unsigned", row["fail_closed"])
        signed = insert_v2_block(data, fake_cert_der("Companion"))
        path = self._write("clean-signed.apk", signed)
        row = apk_review.review_apk(path)
        self.assertEqual(apk_review.DECISION_ACCEPT, row["decision"])
        self.assertEqual(EXPECTED, row["package"])
        self.assertEqual(["android.permission.CAMERA"], row["permissions"])
        self.assertEqual("v2", row["signing"]["scheme"])
        self.assertEqual("Companion", row["signing"]["subject"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
        self.assertEqual(path.stat().st_size, row["bytes"])

    def test_fail_closed_manage_external_storage(self) -> None:
        data = insert_v2_block(
            make_apk(EXPECTED, ["android.permission.MANAGE_EXTERNAL_STORAGE"]),
            fake_cert_der())
        row = apk_review.review_apk(self._write("allfiles.apk", data))
        self.assertEqual(apk_review.DECISION_REJECT, row["decision"])
        self.assertIn("android.permission.MANAGE_EXTERNAL_STORAGE",
                      row["fail_closed"])

    def test_fail_closed_install_packages(self) -> None:
        data = insert_v2_block(
            make_apk(EXPECTED, ["android.permission.INSTALL_PACKAGES"]),
            fake_cert_der())
        row = apk_review.review_apk(self._write("priv.apk", data))
        self.assertEqual(apk_review.DECISION_REJECT, row["decision"])
        self.assertIn("android.permission.INSTALL_PACKAGES", row["fail_closed"])

    def test_fail_closed_device_admin_and_query_all(self) -> None:
        data = insert_v2_block(
            make_apk(EXPECTED, [
                "android.permission.BIND_DEVICE_ADMIN",
                "android.permission.QUERY_ALL_PACKAGES",
            ]),
            fake_cert_der())
        row = apk_review.review_apk(self._write("admin.apk", data))
        self.assertEqual(apk_review.DECISION_REJECT, row["decision"])
        self.assertIn("android.permission.BIND_DEVICE_ADMIN", row["fail_closed"])
        self.assertIn("android.permission.QUERY_ALL_PACKAGES", row["fail_closed"])

    def test_flag_request_install_packages(self) -> None:
        data = insert_v2_block(
            make_apk(EXPECTED, ["android.permission.REQUEST_INSTALL_PACKAGES"]),
            fake_cert_der())
        row = apk_review.review_apk(self._write("flag.apk", data))
        self.assertEqual(apk_review.DECISION_FLAG, row["decision"])
        self.assertIn("android.permission.REQUEST_INSTALL_PACKAGES", row["flags"])
        self.assertEqual([], row["fail_closed"])

    def test_wrong_package_id_rejects(self) -> None:
        data = insert_v2_block(
            make_apk("com.example.other", ["android.permission.CAMERA"]),
            fake_cert_der())
        row = apk_review.review_apk(self._write("other.apk", data))
        self.assertEqual(apk_review.DECISION_REJECT, row["decision"])
        self.assertIn("package_id", row["fail_closed"])

    def test_jsonl_has_no_apk_bytes(self) -> None:
        data = insert_v2_block(
            make_apk(EXPECTED, ["android.permission.CAMERA"]),
            fake_cert_der("Companion"))
        path = self._write("log.apk", data)
        jsonl = self.dir / "apk_review.jsonl"
        row = apk_review.review_apk(path)
        apk_review.append_review(row, jsonl)
        text = jsonl.read_text(encoding="utf8")
        stored = json.loads(text)
        self.assertEqual(row["sha256"], stored["sha256"])
        self.assertNotIn(data[:20].hex(), text)
        self.assertNotIn("apk_bytes", stored)
        self.assertNotIn("blob", stored)

    def test_cli_exit_codes_and_no_jsonl_option(self) -> None:
        signed = insert_v2_block(
            make_apk(EXPECTED, ["android.permission.CAMERA"]),
            fake_cert_der())
        good = self._write("cli-good.apk", signed)
        bad = self._write(
            "cli-bad.apk",
            insert_v2_block(
                make_apk(EXPECTED, ["android.permission.MANAGE_EXTERNAL_STORAGE"]),
                fake_cert_der()),
        )
        flagged = self._write(
            "cli-flag.apk",
            insert_v2_block(
                make_apk(EXPECTED, ["android.permission.REQUEST_INSTALL_PACKAGES"]),
                fake_cert_der()),
        )
        jsonl = self.dir / "out.jsonl"
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            self.assertEqual(0, apk_review.main([str(good), "--jsonl", str(jsonl)]))
            self.assertEqual(1, apk_review.main([str(bad), "--jsonl", str(jsonl)]))
            self.assertEqual(2, apk_review.main([str(flagged), "--jsonl", str(jsonl)]))
            self.assertEqual(0, apk_review.main([str(good), "--no-jsonl"]))
        finally:
            sys.stdout = old
        lines = jsonl.read_text(encoding="utf8").strip().splitlines()
        self.assertEqual(3, len(lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
