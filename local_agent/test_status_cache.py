from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import server


class StatusCacheTests(unittest.TestCase):
    def setUp(self):
        server._status_cache = None
        server._status_cache_at = 0.0

    def test_status_uses_one_router_probe_inside_the_short_ttl(self):
        status = {"tier": "gpu", "model": "test"}
        with patch.object(server.router, "status", return_value=status) as probe, \
             patch.object(server.time, "monotonic", side_effect=[100.0, 101.0]):
            first = server.app_status()
            second = server.app_status()
        self.assertEqual(probe.call_count, 1)
        self.assertEqual(first["app_revision"], server.APP_REVISION)
        self.assertEqual(second["tier"], "gpu")
        self.assertIn("loop_engineering", first)
        self.assertFalse(first["loop_engineering"]["enabled"])

    def test_status_refreshes_after_the_ttl(self):
        with patch.object(server.router, "status", side_effect=[{"tier": "gpu"}, {"tier": "cpu"}]) as probe, \
             patch.object(server.time, "monotonic", side_effect=[100.0, 103.0]):
            self.assertEqual(server.app_status()["tier"], "gpu")
            self.assertEqual(server.app_status()["tier"], "cpu")
        self.assertEqual(probe.call_count, 2)


if __name__ == "__main__":
    unittest.main()
