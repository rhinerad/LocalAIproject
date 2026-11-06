r"""Qwythos farm task must pin keep_alive to the 30m CPU-tier convention.

Correct invocation — from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_qwythos_keep_alive -v
"""
from __future__ import annotations

import sys
import unittest
from unittest.mock import patch

try:
    import local_agent.worker_farm  # noqa: F401
except ModuleNotFoundError as exc:
    if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
        raise
    sys.stderr.write(
        "ERROR: run from the repository root with the farm venv:\n"
        "  local_agent\\worker_farm\\.venv\\Scripts\\python.exe -m unittest "
        "local_agent.worker_farm.test_qwythos_keep_alive -v\n"
    )
    raise SystemExit(2) from exc

from local_agent.worker_farm import tasks


class QwythosKeepAliveTests(unittest.TestCase):
    def test_constant_is_30m(self):
        self.assertEqual("30m", tasks._QWYTHOS_KEEP_ALIVE)

    def test_evaluate_passes_keep_alive_30m(self):
        captured = {}

        def _chat(*_a, **kwargs):
            captured.update(kwargs)
            return "OK", []

        with patch.object(tasks, "_use_local_agent_imports"), \
             patch("ollama_client.chat", side_effect=_chat), \
             patch("router._running_models", return_value=[]), \
             patch("router.QWYTHOS_MODEL", "richardyoung/qwythos-9b-abliterated:latest"):
            result = tasks._qwythos_evaluate(
                {"messages": [{"role": "user", "content": "Reply OK."}]}
            )
        self.assertEqual("30m", captured.get("keep_alive"))
        self.assertEqual("OK", result["content"])


if __name__ == "__main__":
    unittest.main()
