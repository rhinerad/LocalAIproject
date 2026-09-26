"""Queue judge_evaluation jobs for real local-agent chat transcripts.

Per the operator's own explicit 2026-09-02 decision, real transcripts
(including sensitive/NSFW content already present in local_agent/chats/) are
allowed to reach any credentialed worker machine with no filtering -- see
CHANGELOG/2026-09-02c_judge_evaluation_workflow.md. This script only reads
already-saved local chat files and submits them to the `judge` queue; it
never edits a chat, never touches agent.py, memory, or Chroma, and produces
no side effect beyond queuing a task and updating its own small ledger.

Designed to be re-run repeatedly (e.g. from a scheduled task or cron-alike):
each run only queues chats that are new or have changed since they were last
queued, so as conversation volume grows the queue naturally keeps refilling
-- this is the "always stay busy, scales with more machines" job source for
the worker farm's judge_evaluation workflow.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .celery_app import app

HERE = Path(__file__).resolve().parent
CHATS_DIR = HERE.parent / "chats"
LEDGER_PATH = HERE / "runtime" / "judge_ledger.json"


def _load_ledger() -> dict:
    if not LEDGER_PATH.is_file():
        return {}
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(ledger, indent=2, sort_keys=True), encoding="utf-8")


def _candidate_chats() -> list[Path]:
    if not CHATS_DIR.is_dir():
        return []
    return sorted(CHATS_DIR.glob("*.json"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                         help="show what would be queued without submitting")
    parser.add_argument("--limit", type=int, default=0,
                         help="queue at most this many chats this run (0 = no limit)")
    args = parser.parse_args()

    if app is None and not args.dry_run:
        raise SystemExit("Broker configuration/Celery is unavailable; run doctor first.")

    ledger = _load_ledger()
    queued, skipped, errors = 0, 0, 0

    for path in _candidate_chats():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"SKIP (unreadable) {path.name}: {exc}")
            errors += 1
            continue

        chat_id = str(data.get("id") or path.stem)
        updated = data.get("updated")
        messages = data.get("messages") or []
        if not messages:
            continue

        prior = ledger.get(chat_id)
        if prior is not None and prior.get("updated") == updated:
            skipped += 1
            continue

        if args.limit and queued >= args.limit:
            break

        if args.dry_run:
            print(f"WOULD QUEUE {chat_id} ({len(messages)} messages, updated={updated})")
            queued += 1
            continue

        envelope = {"chat_id": chat_id, "messages": messages}
        async_result = app.send_task(
            "local_agent.worker_farm.tasks.judge_transcript", args=[envelope], queue="judge"
        )
        ledger[chat_id] = {"updated": updated, "task_id": async_result.id}
        print(f"QUEUED {chat_id} -> task {async_result.id}")
        queued += 1

    if not args.dry_run:
        _save_ledger(ledger)

    print(f"\nqueued={queued} skipped(unchanged)={skipped} errors={errors} "
          f"total_chats={len(_candidate_chats())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
