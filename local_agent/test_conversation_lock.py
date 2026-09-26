#!/usr/bin/env python3
"""Concurrent conversation updates must not drop messages or metadata."""
from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import store


class ConversationLockTests(unittest.TestCase):
    def test_overlapping_appends_keep_both_messages(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.object(store, "DIR", Path(td)):
            conv = store.create("seed")
            cid = conv["id"]
            started = threading.Event()
            release = threading.Event()

            def hold() -> None:
                with store.conversation_lock(cid):
                    loaded = store.load(cid)
                    assert loaded is not None
                    loaded["messages"].append({
                        "role": "user", "content": "first", "at": 1, "source": "desktop",
                    })
                    started.set()
                    self.assertTrue(release.wait(5))
                    store.save(loaded)

            def other() -> None:
                self.assertTrue(started.wait(5))
                store.append(cid, "user", "second")

            first = threading.Thread(target=hold)
            second = threading.Thread(target=other)
            first.start()
            second.start()
            self.assertTrue(started.wait(5))
            second.join(0.2)
            self.assertTrue(second.is_alive())
            release.set()
            first.join(5)
            second.join(5)
            messages = [item["content"] for item in store.load(cid)["messages"]]
            self.assertEqual(["first", "second"], messages)

    def test_rename_survives_a_concurrent_append(self) -> None:
        with tempfile.TemporaryDirectory() as td, patch.object(store, "DIR", Path(td)):
            conv = store.create("seed")
            cid = conv["id"]
            barrier = threading.Barrier(2)

            def rename() -> None:
                barrier.wait(5)
                store.rename(cid, "kept title")

            def append() -> None:
                barrier.wait(5)
                store.append(cid, "user", "kept message")

            threads = [threading.Thread(target=rename), threading.Thread(target=append)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(5)
            loaded = store.load(cid)
            self.assertEqual("kept title", loaded["title"])
            self.assertIn("kept message", [item["content"] for item in loaded["messages"]])


if __name__ == "__main__":
    unittest.main()
