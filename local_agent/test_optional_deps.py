"""Verify that missing optional packages degrade gracefully, never crash.

The fragility: exemplar_embeddings and feedback_manager had unguarded top-level
imports of chromadb and cryptography. A missing package caused the whole agent
and HTTP server to fail to import, with a traceback naming a vector database
rather than the real problem.

The fix: ImportError at module level sets a flag; every public function returns
a clear, actionable message rather than raising. These tests pin that contract
so the regression cannot return.
"""
import importlib
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

_SENTINEL = object()


def _reload_without(module_name: str, blocked: list[str]):
    """Reload a module as if the listed top-level packages were not installed.

    Setting sys.modules[pkg] = None makes ``import pkg`` raise ImportError.
    Sub-packages (pkg.*) are also removed so Python does not bypass the parent
    block by finding them already cached.
    """
    # Remove the target module so importlib executes it fresh.
    saved_mod = sys.modules.pop(module_name, None)

    # Block each top-level package by setting it to None in sys.modules.
    saved_tops = {}
    for pkg in blocked:
        saved_tops[pkg] = sys.modules.get(pkg, _SENTINEL)
        sys.modules[pkg] = None  # type: ignore[assignment]

    # Remove sub-packages (pkg.*) so the real implementations are not returned
    # from cache before Python even checks the None-blocked parent.
    saved_subs = {}
    for key in list(sys.modules):
        if any(key.startswith(p + ".") for p in blocked):
            saved_subs[key] = sys.modules.pop(key)

    try:
        return importlib.import_module(module_name)
    finally:
        # Restore everything to its pre-test state.
        for pkg, val in saved_tops.items():
            if val is _SENTINEL:
                sys.modules.pop(pkg, None)
            else:
                sys.modules[pkg] = val
        sys.modules.update(saved_subs)
        sys.modules.pop(module_name, None)
        if saved_mod is not None:
            sys.modules[module_name] = saved_mod


class TestChromadbGuard(unittest.TestCase):
    """exemplar_embeddings must load and degrade cleanly when chromadb is absent."""

    def setUp(self):
        self.mod = _reload_without("exemplar_embeddings", ["chromadb"])

    def test_flag_is_false(self):
        self.assertFalse(self.mod._CHROMADB_AVAILABLE)

    def test_reason_names_the_package(self):
        self.assertIn("chromadb", self.mod._CHROMADB_REASON)

    def test_retrieve_raises_with_reason(self):
        # Must not silently return []. Raises RuntimeError naming the package.
        with self.assertRaises(RuntimeError) as ctx:
            self.mod.retrieve("query", ["video_prompt"])
        self.assertIn("chromadb", str(ctx.exception))

    def test_semantic_duplicate_returns_unavailable(self):
        result = self.mod.semantic_duplicate("video_prompt", "test content")
        self.assertFalse(result.get("available", True),
                         "semantic_duplicate must report available=False")
        self.assertIn("reason", result)
        self.assertIn("chromadb", result["reason"])

    def test_embed_record_returns_unavailable(self):
        result = self.mod.embed_record({"status": "approved", "id": "x",
                                        "content": "y", "category": "video_prompt"})
        self.assertNotEqual(result.get("status"), "embedded")
        self.assertIn("reason", result)
        self.assertIn("chromadb", result["reason"])

    def test_sync_approved_returns_unavailable(self):
        result = self.mod.sync_approved()
        self.assertTrue(result.get("unavailable"),
                        "sync_approved must set unavailable=True")
        self.assertIn("reason", result)
        self.assertEqual(result["embedded"], 0)

    def test_start_worker_does_not_crash(self):
        # No-op when chromadb absent; must not raise.
        self.mod.start_worker()


class TestCryptographyGuard(unittest.TestCase):
    """feedback_manager must load and degrade cleanly when cryptography is absent."""

    def setUp(self):
        self.mod = _reload_without("feedback_manager", ["cryptography"])

    def test_flag_is_false(self):
        self.assertFalse(self.mod._CRYPTOGRAPHY_AVAILABLE)

    def test_reason_names_the_package(self):
        self.assertIn("cryptography", self.mod._CRYPTOGRAPHY_REASON)

    def test_decrypt_envelope_returns_unavailable(self):
        import pathlib, tempfile
        # The guard fires before the file is read.
        dummy = pathlib.Path(tempfile.mktemp(suffix=".json"))
        result = self.mod.decrypt_envelope(dummy)
        self.assertFalse(result.get("available", True),
                         "decrypt_envelope must report available=False")
        self.assertIn("reason", result)
        self.assertIn("cryptography", result["reason"])

    def test_status_reports_unavailable(self):
        result = self.mod.status()
        self.assertFalse(result.get("available", True),
                         "status must report available=False")
        self.assertIn("cryptography", result.get("last_error", ""))

    def test_start_idle_worker_does_not_crash(self):
        self.mod.start_idle_worker()

    def test_flush_pending_raises_runtime_not_import_error(self):
        # _encrypt raises RuntimeError; flush_pending re-raises it.
        # The test confirms no ImportError or AttributeError — just a clear RuntimeError.
        self.mod.enqueue({"id": "test", "rating": "positive", "mode": "rule_only",
                          "timestamp": "2026-01-01T00:00:00+00:00",
                          "conversation_id": "x", "message_id": "y",
                          "query_fingerprint": "z", "distilled_rule": "",
                          "category": "tool_execution", "is_encrypted": False,
                          "sanitized_payload": {}})
        with self.assertRaises(RuntimeError) as ctx:
            self.mod.flush_pending(force=True)
        self.assertIn("cryptography", str(ctx.exception))


class TestCapabilitiesReporting(unittest.TestCase):
    """capabilities.all_capabilities() must name both optional components."""

    def test_exemplar_retrieval_is_reported(self):
        import capabilities
        caps = capabilities.all_capabilities()
        self.assertIn("exemplar_retrieval", caps,
                      "all_capabilities must include exemplar_retrieval")
        entry = caps["exemplar_retrieval"]
        self.assertIn("available", entry)
        self.assertIn("reason", entry)

    def test_feedback_encryption_is_reported(self):
        import capabilities
        caps = capabilities.all_capabilities()
        self.assertIn("feedback_encryption", caps,
                      "all_capabilities must include feedback_encryption")
        entry = caps["feedback_encryption"]
        self.assertIn("available", entry)
        self.assertIn("reason", entry)

    def test_capability_names_chromadb_when_absent(self):
        import capabilities, importlib.util
        if importlib.util.find_spec("chromadb") is not None:
            self.skipTest("chromadb is installed; absence path not reachable here")
        entry = capabilities.capability("exemplar_retrieval")
        self.assertFalse(entry["available"])
        self.assertIn("chromadb", entry.get("install", ""))

    def test_capability_names_cryptography_when_absent(self):
        import capabilities, importlib.util
        if importlib.util.find_spec("cryptography") is not None:
            self.skipTest("cryptography is installed; absence path not reachable here")
        entry = capabilities.capability("feedback_encryption")
        self.assertFalse(entry["available"])
        self.assertIn("cryptography", entry.get("install", ""))

    def test_exemplar_retrieval_when_present(self):
        import capabilities, importlib.util
        if importlib.util.find_spec("chromadb") is None:
            self.skipTest("chromadb is not installed")
        entry = capabilities.capability("exemplar_retrieval")
        self.assertTrue(entry["available"])
        self.assertIn("chromadb", entry.get("reason", ""))

    def test_feedback_encryption_when_present(self):
        import capabilities, importlib.util
        if importlib.util.find_spec("cryptography") is None:
            self.skipTest("cryptography is not installed")
        entry = capabilities.capability("feedback_encryption")
        self.assertTrue(entry["available"])
        self.assertIn("cryptography", entry.get("reason", ""))


class TestAgentImportsSurvive(unittest.TestCase):
    """agent and server must import successfully even with optional packages blocked."""

    def _run_import(self, extra_stubs: str, module: str) -> subprocess.CompletedProcess:
        stub_block = (
            "import sys\n"
            f"{extra_stubs}\n"
            f"import {module}\n"
            "print('ok')\n"
        )
        return subprocess.run(
            [sys.executable, "-c", stub_block],
            capture_output=True, text=True, cwd=str(HERE), timeout=30,
        )

    @staticmethod
    def _block(pkg: str) -> str:
        return (
            f"import sys\n"
            f"sys.modules['{pkg}'] = None\n"
            f"for _k in list(sys.modules):\n"
            f"    if _k.startswith('{pkg}.'): sys.modules[_k] = None\n"
        )

    def test_agent_imports_without_chromadb(self):
        result = self._run_import(self._block("chromadb"), "agent")
        self.assertIn("ok", result.stdout,
                      f"agent failed to import without chromadb:\n{result.stderr[:2000]}")

    def test_server_imports_without_chromadb(self):
        result = self._run_import(self._block("chromadb"), "server")
        self.assertIn("ok", result.stdout,
                      f"server failed to import without chromadb:\n{result.stderr[:2000]}")

    def test_server_imports_without_cryptography(self):
        result = self._run_import(self._block("cryptography"), "server")
        self.assertIn("ok", result.stdout,
                      f"server failed to import without cryptography:\n{result.stderr[:2000]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
