#!/usr/bin/env python3
"""Workstation ADB install wrapper (companion PR 2). Refuse by default.

Installs only when serial + ro.build.fingerprint + APK SHA-256 match an
unrevoked row in runtime/lxmf/adb_trusted_devices.json. Default is off:
missing ledger, missing approval, mismatch, unauthorized, or more than one
authorized device → exit 2 and never run `adb install`.

Not imported by lxmf_agent.py. Not in the Android tree. No scheduled task.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Sequence

from apk_review import sha256_file as _sha256_file

HERE = Path(__file__).resolve().parent
DEFAULT_LEDGER = HERE / "runtime" / "lxmf" / "adb_trusted_devices.json"
DEFAULT_JSONL = HERE / "runtime" / "lxmf" / "adb_install.jsonl"

EXIT_OK = 0
EXIT_USAGE = 1
EXIT_REFUSE = 2
EXIT_ADB = 3

OUTCOME_REFUSED = "refused"
OUTCOME_DRY_RUN = "dry_run"
OUTCOME_INSTALLED = "installed"
OUTCOME_ADB_FAILED = "adb_failed"

AdbRunner = Callable[..., subprocess.CompletedProcess]


def sha256_file(path: Path) -> str:
    return _sha256_file(path)


def run_adb(
    adb: str | Path,
    args: Sequence[str],
    *,
    timeout: float = 30,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(adb), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def parse_adb_devices(text: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("List of devices"):
            continue
        if stripped.startswith("*"):
            continue
        parts = stripped.split()
        if len(parts) < 2:
            continue
        rows.append((parts[0], parts[1]))
    return rows


def load_ledger(path: Path) -> tuple[dict | None, list[str]]:
    if not path.is_file():
        return None, ["ledger_missing"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None, ["ledger_unparsed"]
    if not isinstance(data, dict):
        return None, ["ledger_unparsed"]
    if data.get("version") != 1:
        return None, ["ledger_version"]
    devices = data.get("devices")
    if not isinstance(devices, dict):
        return None, ["ledger_unparsed"]
    return data, []


def approval_reasons(row: dict | None, *, serial: str, sha256: str) -> list[str]:
    if row is None:
        return ["no_approval_row"]
    if not isinstance(row, dict):
        return ["no_approval_row"]
    reasons: list[str] = []
    row_serial = row.get("serial")
    if row_serial is not None and str(row_serial) != serial:
        reasons.append("ledger_serial_mismatch")
    if "approved_at" not in row or row.get("approved_at") is None:
        reasons.append("approved_at_missing")
    revoked = row.get("revoked_at")
    if revoked is not None and revoked != "":
        reasons.append("revoked")
    expected = str(row.get("approved_apk_sha256") or "").strip().lower()
    if not expected:
        reasons.append("sha256_mismatch")
    elif expected != sha256.lower():
        reasons.append("sha256_mismatch")
    fingerprint = row.get("build_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint.strip():
        reasons.append("fingerprint_unverified")
    return reasons


def devices_reasons(rows: list[tuple[str, str]], serial: str) -> list[str]:
    unauthorized = {s for s, st in rows if st == "unauthorized"}
    authorized = [s for s, st in rows if st == "device"]
    if serial in unauthorized:
        return ["unauthorized"]
    if len(authorized) == 0:
        return ["no_device"]
    if len(authorized) != 1:
        return ["multiple_devices"]
    if authorized[0] != serial:
        return ["serial_mismatch"]
    return []


def _log_row(
    *,
    path: Path,
    serial: str,
    sha256: str,
    outcome: str,
    reasons: list[str],
    fingerprint_seen: str | None,
    approved_apk_sha256: str | None,
    size: int,
) -> dict:
    return {
        "at": time.time(),
        "path": str(path),
        "bytes": size,
        "serial": serial,
        "sha256": sha256,
        "approved_apk_sha256": approved_apk_sha256,
        "fingerprint_seen": fingerprint_seen,
        "outcome": outcome,
        "reasons": list(reasons),
    }


def append_log(row: dict, jsonl_path: Path | None = None) -> Path:
    dest = Path(jsonl_path) if jsonl_path else DEFAULT_JSONL
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(row)
    with dest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    return dest


def trusted_install(
    apk: Path,
    serial: str,
    *,
    ledger_path: Path | None = None,
    adb: str | Path = "adb",
    dry_run: bool = False,
    adb_runner: AdbRunner | None = None,
    jsonl_path: Path | None = None,
    write_jsonl: bool = True,
) -> dict:
    """Verify ledger + live adb, then optionally `adb install -r`.

    Never includes APK bytes in the returned row. Exit policy is encoded in
    `outcome` / `reasons`; the CLI maps those to 0 / 2 / 3.
    """
    runner = adb_runner or run_adb
    apk = Path(apk)
    serial = str(serial)
    ledger_path = Path(ledger_path) if ledger_path else DEFAULT_LEDGER
    reasons: list[str] = []
    fingerprint_seen: str | None = None
    approved_hash: str | None = None
    size = apk.stat().st_size if apk.is_file() else 0
    sha = ""

    if not apk.is_file():
        reasons.append("apk_missing")
        row = _log_row(
            path=apk, serial=serial, sha256=sha, outcome=OUTCOME_REFUSED,
            reasons=reasons, fingerprint_seen=None, approved_apk_sha256=None,
            size=size)
        if write_jsonl:
            append_log(row, jsonl_path)
        return row

    sha = sha256_file(apk)
    ledger, ledger_reasons = load_ledger(ledger_path)
    reasons.extend(ledger_reasons)
    row_data = None
    if ledger is not None:
        devices = ledger.get("devices") or {}
        raw = devices.get(serial)
        row_data = raw if isinstance(raw, dict) else None
        if row_data is not None:
            approved_hash = str(row_data.get("approved_apk_sha256") or "") or None
        reasons.extend(approval_reasons(row_data, serial=serial, sha256=sha))

    expected_fp = ""
    if row_data and isinstance(row_data.get("build_fingerprint"), str):
        expected_fp = row_data["build_fingerprint"].strip()

    if not reasons:
        try:
            proc = runner(adb, ["devices"], timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            reasons.append("adb_failed")
            proc = None
        if proc is not None:
            if proc.returncode != 0:
                reasons.append("adb_failed")
            else:
                reasons.extend(devices_reasons(parse_adb_devices(proc.stdout or ""), serial))

    if not reasons and expected_fp:
        try:
            proc = runner(
                adb, ["-s", serial, "shell", "getprop", "ro.build.fingerprint"],
                timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            reasons.append("fingerprint_unverified")
            proc = None
        if proc is not None:
            fingerprint_seen = (proc.stdout or "").strip()
            if proc.returncode != 0 or not fingerprint_seen:
                reasons.append("fingerprint_unverified")
            elif fingerprint_seen != expected_fp:
                reasons.append("fingerprint_mismatch")

    if not reasons:
        sha_again = sha256_file(apk)
        if sha_again.lower() != sha.lower():
            sha = sha_again
            reasons.append("sha256_changed")
        elif approved_hash and sha_again.lower() != approved_hash.strip().lower():
            sha = sha_again
            reasons.append("sha256_mismatch")

    if reasons:
        outcome = OUTCOME_REFUSED
    elif dry_run:
        outcome = OUTCOME_DRY_RUN
    else:
        try:
            proc = runner(
                adb, ["-s", serial, "install", "-r", str(apk)],
                timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            outcome = OUTCOME_ADB_FAILED
            reasons.append("adb_install_failed")
            proc = None
        if proc is not None:
            if proc.returncode != 0:
                outcome = OUTCOME_ADB_FAILED
                reasons.append("adb_install_failed")
            else:
                outcome = OUTCOME_INSTALLED

    row = _log_row(
        path=apk, serial=serial, sha256=sha, outcome=outcome, reasons=reasons,
        fingerprint_seen=fingerprint_seen, approved_apk_sha256=approved_hash,
        size=size)
    if write_jsonl:
        append_log(row, jsonl_path)
    return row


def _print_row(row: dict) -> None:
    print(f"path      : {row['path']}")
    print(f"bytes     : {row['bytes']}")
    print(f"serial    : {row['serial']}")
    print(f"sha256    : {row['sha256']}")
    print(f"approved  : {row.get('approved_apk_sha256')}")
    print(f"fp_seen   : {row.get('fingerprint_seen')}")
    print(f"outcome   : {row['outcome']}")
    print(f"reasons   : {', '.join(row.get('reasons') or []) or '(none)'}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Refuse-by-default adb install against adb_trusted_devices.json.")
    parser.add_argument("apk", type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--jsonl", type=Path, default=DEFAULT_JSONL)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--dry-run", action="store_true",
                        help="verify serial/fingerprint/hash; do not adb install")
    parser.add_argument("--no-jsonl", action="store_true")
    args = parser.parse_args(argv)
    if not args.serial.strip():
        print("serial is required", file=sys.stderr)
        return EXIT_USAGE
    row = trusted_install(
        args.apk,
        args.serial.strip(),
        ledger_path=args.ledger,
        adb=args.adb,
        dry_run=args.dry_run,
        jsonl_path=args.jsonl,
        write_jsonl=not args.no_jsonl,
    )
    if not args.no_jsonl:
        print(f"jsonl     : {args.jsonl}")
    _print_row(row)
    if row["outcome"] == OUTCOME_REFUSED:
        return EXIT_REFUSE
    if row["outcome"] == OUTCOME_ADB_FAILED:
        return EXIT_ADB
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
