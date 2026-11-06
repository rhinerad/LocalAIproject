#!/usr/bin/env python3
"""Private-safe evaluation harness for the MiniMax H3 prompt validator.

The production prompt corpus remains private. Reports contain only aggregate
counts, hashes, elapsed time, and validator error codes -- never prompt text or
file names. This makes a run reproducible locally while leaving a safe evidence
trail for the portfolio track.

Usage:
    python local_agent\\h3_evaluation.py --dir outputs\\equal_shares\\prompts_native_r2v
    python local_agent\\h3_evaluation.py --dir ... --output runtime\\evaluations\\h3.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from validate_h3_prompt import validate

FORMAT_VERSION = "h3-eval-v1"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def corpus_fingerprint(files: list[Path]) -> str:
    """Hash names plus bytes deterministically without writing either to output."""
    digest = hashlib.sha256()
    for path in files:
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validator_fingerprint() -> str:
    return sha256_bytes(Path(__file__).with_name("validate_h3_prompt.py").read_bytes())


def error_code(message: str) -> str:
    return message.split(":", 1)[0]


def synthetic_negative_suite(valid_text: str) -> dict[str, list[str]]:
    """Create non-sensitive negative controls from an already-valid prompt."""
    return {
        "prefixed_wrapper": validate("REFERENCE JOBS\n" + valid_text, "synthetic_wrapper").errors,
        "missing_section": validate(valid_text.replace("summary:", "summary_removed:", 1),
                                    "synthetic_section").errors,
        "zero_based_tag": validate(valid_text.replace("<Picture 1>", "<Picture 0>", 1),
                                   "synthetic_tag").errors,
        "beat_bracket": validate(valid_text + "\n[0-1 s]\n", "synthetic_timing").errors,
    }


def evaluate(directory: Path) -> dict[str, Any]:
    files = sorted(path for path in directory.glob("*.txt") if path.is_file())
    if not files:
        raise ValueError(f"No .txt prompts found in {directory}")

    started = time.perf_counter()
    reports = [validate(path.read_text(encoding="utf-8"), path.name) for path in files]
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    valid = [report for report in reports if report.ok]
    errors = Counter(error_code(error) for report in reports for error in report.errors)
    warnings = Counter(error_code(warning) for report in reports for warning in report.warnings)

    negative_errors = synthetic_negative_suite(files[0].read_text(encoding="utf-8"))
    negative_detected = {
        case: sorted({error_code(error) for error in result})
        for case, result in negative_errors.items()
    }
    negative_ok = all(result for result in negative_errors.values())

    return {
        "format_version": FORMAT_VERSION,
        "timestamp_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "validator_sha256": validator_fingerprint(),
        "corpus_sha256": corpus_fingerprint(files),
        "corpus_file_count": len(files),
        "valid_count": len(valid),
        "invalid_count": len(files) - len(valid),
        "elapsed_ms": elapsed_ms,
        "error_codes": dict(sorted(errors.items())),
        "warning_codes": dict(sorted(warnings.items())),
        "synthetic_negative_controls": negative_detected,
        "synthetic_negative_controls_passed": negative_ok,
        "privacy": "No prompt text, file names, paths, or media identifiers are emitted.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, type=Path, help="Private prompt corpus directory")
    parser.add_argument("--output", type=Path, help="Optional JSON evidence report path")
    args = parser.parse_args()

    result = evaluate(args.dir)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if result["invalid_count"] == 0 and result["synthetic_negative_controls_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
