"""Strict, no-network acceptance check for operator-approved calibration JSONL."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from validate_calibration_pairs import PATH_RE, SECRET_RE

SCHEMA_VERSION = "projected-abliteration-v1"
CATEGORY = "contrastive_refusal"
SOURCE = "operator_authored"
PAIR_ID_RE = re.compile(r"^pa-[0-9]{3,}$")
APPROVAL_RE = re.compile(r"^operator-approval-[0-9]{8}(?:-[a-z0-9][a-z0-9-]{0,63})?$", re.I)


def validate(path: Path, minimum: int = 32) -> dict[str, object]:
    seen: set[str] = set()
    approval_ids: set[str] = set()
    count = 0
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError(f"line {lineno}: expected JSON object")
        for key in ("pair_id", "harmful", "harmless", "category", "source", "approval_id", "schema_version"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"line {lineno}: {key} must be a non-empty string")
        if row.get("operator_approved") is not True:
            raise ValueError(f"line {lineno}: operator_approved must be true")
        if not PAIR_ID_RE.fullmatch(row["pair_id"]):
            raise ValueError(f"line {lineno}: invalid pair_id")
        if row["pair_id"] in seen:
            raise ValueError(f"line {lineno}: duplicate pair_id {row['pair_id']}")
        if row["category"] != CATEGORY or row["source"] != SOURCE:
            raise ValueError(f"line {lineno}: category/source are not approved values")
        if row["schema_version"] != SCHEMA_VERSION:
            raise ValueError(f"line {lineno}: unexpected schema_version")
        if not APPROVAL_RE.fullmatch(row["approval_id"]):
            raise ValueError(f"line {lineno}: invalid approval_id")
        if any(PATH_RE.search(row[key]) or SECRET_RE.search(row[key]) for key in ("harmful", "harmless")):
            raise ValueError(f"line {lineno}: path or secret-like content refused")
        if len(row["harmful"].split()) < 3 or len(row["harmless"].split()) < 3:
            raise ValueError(f"line {lineno}: prompts are too short for a contrastive pair")
        seen.add(row["pair_id"])
        approval_ids.add(row["approval_id"])
        count += 1
    if count < minimum:
        raise ValueError(f"need at least {minimum} approved pairs, found {count}")
    if len(approval_ids) != 1:
        raise ValueError("all pairs must share one approval_id")
    return {"pairs": count, "approval_id": next(iter(approval_ids)), "status": "approved_input"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--minimum", type=int, default=32)
    args = parser.parse_args()
    print(json.dumps(validate(args.path, args.minimum), indent=2))
