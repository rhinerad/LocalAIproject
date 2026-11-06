"""Validate an operator-supplied, benign calibration-pair JSONL file.

This only checks structure and obvious secret/path leakage. It does not call a
model, download data, or decide whether a pair is scientifically appropriate.

Draft mode (--draft) is for UNAPPROVED review-only JSONL: it requires
operator_approved JSON false and approval_id JSON null on every row, and
rejects operator_approved true or any non-null approval_id. Draft mode never
authorizes GPU work.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

PATH_RE = re.compile(r"(?:[A-Za-z]:[\/]|/Users/|/home/)")
SECRET_RE = re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]")


def validate(path: Path, minimum: int = 8, draft: bool = False) -> dict[str, object]:
    count = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("harmful", "harmless")):
            raise ValueError(f"line {lineno}: expected string harmful/harmless")
        if any(PATH_RE.search(row[k]) or SECRET_RE.search(row[k]) for k in ("harmful", "harmless")):
            raise ValueError(f"line {lineno}: path or secret-like content refused")
        if not row["harmful"].strip() or not row["harmless"].strip():
            raise ValueError(f"line {lineno}: empty harmful/harmless")
        if draft:
            if "operator_approved" not in row:
                raise ValueError(f"line {lineno}: draft requires operator_approved false")
            if row.get("operator_approved") is True:
                raise ValueError(f"line {lineno}: draft rejects operator_approved true")
            if row.get("operator_approved") is not False:
                raise ValueError(f"line {lineno}: draft requires operator_approved false")
            if "approval_id" not in row:
                raise ValueError(f"line {lineno}: draft requires approval_id null")
            if row.get("approval_id") is not None:
                raise ValueError(f"line {lineno}: draft rejects non-null approval_id")
        count += 1
    if count < minimum:
        raise ValueError(f"need at least {minimum} non-empty pairs, found {count}")
    result: dict[str, object] = {"pairs": count}
    if draft:
        result["status"] = "draft_unapproved"
        result["operator_approved"] = False
        result["approval_id"] = None
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--minimum", type=int, default=8)
    ap.add_argument(
        "--draft",
        action="store_true",
        help="UNAPPROVED draft mode: require operator_approved false and approval_id null",
    )
    args = ap.parse_args()
    print(json.dumps(validate(args.path, minimum=args.minimum, draft=args.draft), indent=2))
