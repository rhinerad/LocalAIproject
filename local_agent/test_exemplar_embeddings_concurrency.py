#!/usr/bin/env python3
"""Exercise foreground exemplar reads against one real background sync cycle."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    import chromadb  # noqa: F401
except ImportError:  # pragma: no cover - matches the optional-dependency contract
    chromadb = None

import exemplar_curator
import exemplar_embeddings as embeddings


class _OneCycleStop:
    """Make the production 20-second worker perform exactly one immediate pass."""

    def __init__(self) -> None:
        self.calls = 0

    def clear(self) -> None:
        return None

    def wait(self, _seconds: float) -> bool:
        self.calls += 1
        return self.calls > 1


@unittest.skipIf(chromadb is None, "chromadb is not installed")
class PersistentClientConcurrencyTests(unittest.TestCase):
    @staticmethod
    def record(identifier: str) -> dict:
        return {
            "id": identifier, "status": "approved", "category": "video_prompt",
            "content": "A woman crosses a quiet studio and pauses at a sunlit window.",
            "source_dataset": "Manual", "license": "Internal", "style_domain": "general",
            "title": "Studio action", "content_fingerprint": identifier,
        }

    def test_background_sync_and_foreground_reads_share_one_store_without_error(self):
        # This initially validates the audit's *unverified* concurrency concern:
        # no exception was reproduced with separate PersistentClient handles.
        # The cache refactor that follows preserves this observable contract.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            approved = root / "approved"
            approved.mkdir()
            record = self.record("stage_video_prompt_concurrent")
            (approved / f"{record['id']}.json").write_text(
                json.dumps(record), encoding="utf-8"
            )
            one_cycle = _OneCycleStop()
            embeddings._reset_client_for_tests()
            with patch.object(embeddings, "DB_DIR", root / "chroma"), \
                 patch.object(exemplar_curator, "APPROVED", approved), \
                 patch.object(embeddings.router, "chat_busy", return_value=False), \
                 patch.object(embeddings.oll, "embed", return_value=[[1.0, 0.0, 0.0]]), \
                 patch.object(embeddings, "_STOP", one_cycle):
                try:
                    embeddings._WORKER = None
                    embeddings.start_worker()
                    worker = embeddings._WORKER
                    self.assertIsNotNone(worker)
                    errors: list[BaseException] = []

                    def foreground() -> None:
                        try:
                            for _ in range(12):
                                embeddings.retrieve("studio action", ["video_prompt"])
                                embeddings.semantic_duplicate("video_prompt", record["content"])
                        except BaseException as exc:  # capture thread failure for assertion
                            errors.append(exc)

                    reader = threading.Thread(target=foreground)
                    reader.start()
                    reader.join(timeout=10)
                    worker.join(timeout=10)
                    self.assertFalse(reader.is_alive(), "foreground read did not finish")
                    self.assertFalse(worker.is_alive(), "one-cycle worker did not finish")
                    self.assertEqual([], errors)
                    self.assertEqual("embedded", json.loads(
                        (approved / f"{record['id']}.json").read_text(encoding="utf-8")
                    )["embedding"]["status"])
                finally:
                    embeddings._reset_client_for_tests()


if __name__ == "__main__":
    unittest.main(verbosity=2)
