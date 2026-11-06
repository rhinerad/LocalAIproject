#!/usr/bin/env python3
"""Evidence-only metrics for an LXMF/LoRa delivery experiment.

The workstation can prove only that it queued an outbound LXMF item.  It cannot
truthfully infer phone delivery from that event.  This utility combines the
append-only scheduler audit with optional operator-recorded phone receipts and
reports the distinction explicitly.  It never sends a message, opens a radio
port, edits a schedule, or contacts a network service.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_AUDIT = HERE / "runtime" / "lxmf" / "phone_schedule_audit.jsonl"


def _records(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.is_file():
        return rows
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            item.setdefault("_line", number)
            rows.append(item)
    return rows


def _key(record: dict) -> tuple[str, int] | None:
    try:
        return str(record["job_id"]), int(record["counter"])
    except (KeyError, TypeError, ValueError):
        return None


def report(audit_path: Path = DEFAULT_AUDIT, receipts_path: Path | None = None,
           close_at: float | None = None) -> dict:
    """Return conservative queue and receipt metrics.

    Receipt records must be JSON Lines with ``job_id``, ``counter`` and
    ``received_at`` (Unix seconds).  Loss is calculated only when the operator
    supplies an explicit ``close_at`` after the controlled test has ended.
    """
    audit = _records(Path(audit_path))
    queued: dict[tuple[str, int], float] = {}
    duplicate_queue_events = 0
    outcomes: dict[str, int] = {}
    for item in audit:
        event = str(item.get("event", "unknown"))
        outcomes[event] = outcomes.get(event, 0) + 1
        if event != "queued":
            continue
        key = _key(item)
        try:
            queued_at = float(item["at"])
        except (KeyError, TypeError, ValueError):
            continue
        if key is None:
            continue
        if key in queued:
            duplicate_queue_events += 1
        else:
            queued[key] = queued_at

    result = {
        "audit_path": str(audit_path),
        "queue_events": outcomes,
        "unique_lxmf_queue_events": len(queued),
        "duplicate_queue_events": duplicate_queue_events,
        "delivery_status": "not_measured_without_phone_receipts",
        "delivery_note": (
            "Queued to LXMF is not proof of radio or phone delivery. "
            "Provide receipt evidence and an explicit test close time to measure loss."),
    }
    if receipts_path is None:
        return result

    receipts = _records(Path(receipts_path))
    received: dict[tuple[str, int], float] = {}
    invalid_receipts = 0
    for item in receipts:
        key = _key(item)
        try:
            received_at = float(item["received_at"])
        except (KeyError, TypeError, ValueError):
            invalid_receipts += 1
            continue
        if key is None:
            invalid_receipts += 1
            continue
        received.setdefault(key, received_at)

    matched = {key: at for key, at in received.items() if key in queued}
    unmatched = len(received) - len(matched)
    latencies = [at - queued[key] for key, at in matched.items() if at >= queued[key]]
    result.update({
        "receipts_path": str(receipts_path),
        "receipt_rows": len(receipts),
        "unique_matched_receipts": len(matched),
        "unmatched_receipts": unmatched,
        "invalid_receipts": invalid_receipts,
        "latency_seconds": ({"min": min(latencies), "median": statistics.median(latencies),
                              "max": max(latencies)} if latencies else None),
    })
    if close_at is None:
        result["delivery_status"] = "receipt_evidence_present_test_not_closed"
        return result

    expected = {key for key, sent_at in queued.items() if sent_at <= float(close_at)}
    delivered = expected & set(matched)
    result.update({
        "delivery_status": "measured_from_operator_receipts",
        "test_closed_at": float(close_at),
        "expected_before_close": len(expected),
        "receipt_confirmed": len(delivered),
        "unconfirmed": len(expected - delivered),
        "observed_loss_percent": (100.0 * len(expected - delivered) / len(expected)
                                  if expected else None),
    })
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize LXMF queue and phone-receipt evidence")
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--receipts", type=Path,
                        help="JSONL: job_id, counter, received_at for each phone receipt")
    parser.add_argument("--close-at", type=float,
                        help="Unix time after the controlled test ended; enables observed-loss calculation")
    args = parser.parse_args()
    print(json.dumps(report(args.audit, args.receipts, args.close_at), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
