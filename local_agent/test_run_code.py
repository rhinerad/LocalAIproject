#!/usr/bin/env python3
"""Stdlib tests for the sandboxed run_code tool. No model is loaded."""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import agent
import remote_security
import sandbox_runner
import tools


class RunCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sandbox"
        self.root.mkdir()
        patcher = patch.object(sandbox_runner, "SANDBOX_ROOT", self.root)
        patcher.start()
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(patcher.stop)

    def _run(self, args: dict) -> dict:
        raw = tools.call("run_code", args)
        self.assertFalse(raw.startswith("ERROR:"), raw)
        return json.loads(raw)

    def test_hello_world_stdout_exit_zero(self) -> None:
        result = self._run({"language": "python", "code": "print('hello-world')"})
        self.assertEqual(0, result["exit_code"])
        self.assertIn("hello-world", result["stdout"])
        self.assertFalse(result["timed_out"])
        self.assertFalse(result["allow_network"])
        self.assertTrue(result["run_dir"].startswith(str(self.root)))

    def test_infinite_loop_hits_timeout_and_is_killed(self) -> None:
        result = self._run({
            "language": "python",
            "code": "while True:\n    pass\n",
            "timeout": 2,
        })
        self.assertTrue(result["timed_out"])
        self.assertNotEqual(0, result["exit_code"])
        self.assertIn("timed out", result["stderr"])
        self.assertGreaterEqual(result["duration"], 1.5)

    def test_script_cannot_read_project_file_outside_run_dir(self) -> None:
        outside = Path(tools.__file__).resolve()
        code = (
            "from pathlib import Path\n"
            f"print(Path(r'{outside}').read_text(encoding='utf-8')[:40])\n"
        )
        result = self._run({"language": "python", "code": code})
        self.assertNotEqual(0, result["exit_code"])
        self.assertNotIn("What the local agent", result["stdout"])
        self.assertIn("outside the run dir", result["stderr"])

    def test_script_cannot_write_outside_run_dir_via_pathlib(self) -> None:
        target = Path(self.tmp.name) / "pwned.txt"
        code = (
            "from pathlib import Path\n"
            f"Path(r'{target}').write_text('pwned')\n"
        )
        result = self._run({"language": "python", "code": code})
        self.assertNotEqual(0, result["exit_code"])
        self.assertIn("outside the run dir", result["stderr"])
        self.assertFalse(target.exists())

    def test_script_cannot_chdir_outside_run_dir(self) -> None:
        code = "import os\nos.chdir(r'" + str(Path(self.tmp.name)) + "')\nprint('chdir-succeeded')\n"
        result = self._run({"language": "python", "code": code})
        self.assertNotEqual(0, result["exit_code"])
        self.assertNotIn("chdir-succeeded", result["stdout"])
        self.assertIn("outside the run dir", result["stderr"])

    def test_ordinary_stdlib_imports_still_work_in_sandbox(self) -> None:
        result = self._run({
            "language": "python",
            "code": "import json, socket, hashlib, collections\nprint('imports-ok')\n",
        })
        self.assertEqual(0, result["exit_code"])
        self.assertIn("imports-ok", result["stdout"])

    def test_path_outside_sandbox_is_refused(self) -> None:
        raw = tools.call("run_code", {
            "language": "python",
            "path": str(HERE / "agent.py"),
        })
        self.assertIn("ERROR:", raw)
        self.assertIn("outside the sandbox", raw)

    def test_equal_shares_path_is_refused(self) -> None:
        raw = tools.call("run_code", {
            "language": "python",
            "path": "outputs/equal_shares/manifest.json",
        })
        self.assertIn("ERROR:", raw)
        self.assertIn("outside the sandbox", raw)

    def test_captured_output_is_size_capped(self) -> None:
        n = sandbox_runner.MAX_OUTPUT_CHARS + 4000
        result = self._run({
            "language": "python",
            "code": f"print('x'*{n})",
        })
        self.assertEqual(0, result["exit_code"])
        self.assertIn("[truncated at", result["stdout"])
        self.assertLessEqual(len(result["stdout"]), sandbox_runner.MAX_OUTPUT_CHARS + 80)

    def test_run_file_written_inside_sandbox(self) -> None:
        run = sandbox_runner.new_run_dir()
        script = run / "main.py"
        script.write_text("print(open('ok.txt').read())\n", encoding="utf-8")
        (run / "ok.txt").write_text("from-run-dir\n", encoding="utf-8")
        result = self._run({
            "language": "python",
            "path": str(script),
        })
        self.assertEqual(0, result["exit_code"])
        self.assertIn("from-run-dir", result["stdout"])

    def test_child_interpreter_cannot_be_started(self) -> None:
        target = Path(self.tmp.name) / "child-wrote.txt"
        escaped = str(target).replace("\\", "\\\\")
        code = (
            "import subprocess, sys\n"
            f"subprocess.check_call([sys.executable, '-c', 'open(\"{escaped}\", \"w\").write(\"x\")'])\n"
        )
        result = self._run({"language": "python", "code": code})
        self.assertNotEqual(0, result["exit_code"])
        self.assertIn("process creation is disabled", result["stderr"])
        self.assertFalse(target.exists())

    def test_parent_secrets_are_not_inherited(self) -> None:
        with patch.dict(os.environ, {"AUDIT_SECRET_TOKEN": "super-secret-value"}):
            result = self._run({
                "language": "python",
                "code": "import os\nprint(os.environ.get('AUDIT_SECRET_TOKEN', ''))\n",
            })
        self.assertEqual(0, result["exit_code"])
        self.assertNotIn("super-secret-value", result["stdout"])

    def test_network_is_disabled(self) -> None:
        result = self._run({
            "language": "python",
            "code": "import socket\nsocket.create_connection(('127.0.0.1', 9), timeout=2)\n",
        })
        self.assertNotEqual(0, result["exit_code"])
        self.assertIn("network is disabled", result["stderr"])

    def test_allow_network_is_refused(self) -> None:
        raw = tools.call("run_code", {"code": "print(1)", "allow_network": True})
        self.assertIn("ERROR:", raw)
        self.assertIn("allow_network", raw)

    def test_node_cannot_write_outside_run_dir(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not on PATH")
        target = Path(self.tmp.name) / "node-wrote.txt"
        code = (
            "const fs=require('fs');\n"
            f"fs.writeFileSync({str(target)!r}, 'x');\n"
            "console.log('wrote');\n"
        )
        result = self._run({"language": "javascript", "code": code})
        self.assertNotEqual(0, result["exit_code"])
        self.assertFalse(target.exists())
        self.assertNotIn("wrote", result["stdout"])

    def test_node_cannot_start_a_child_process(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is not on PATH")
        result = self._run({
            "language": "javascript",
            "code": "require('child_process').execSync('cmd /c echo pwned');\nconsole.log('spawned');\n",
        })
        self.assertNotEqual(0, result["exit_code"])
        self.assertNotIn("spawned", result["stdout"])
        self.assertNotIn("pwned", result["stdout"])

    def test_shell_language_refused(self) -> None:
        raw = tools.call("run_code", {"language": "bash", "code": "echo hi"})
        self.assertIn("ERROR:", raw)
        self.assertIn("unsupported language", raw)

    def test_phone_identity_is_default_denied(self) -> None:
        context = remote_security.ToolContext(source="phone")
        raw = tools.call("run_code", {"code": "print(1)"}, context=context)
        self.assertIn("not permitted", raw)

    def test_run_code_is_registered(self) -> None:
        self.assertIn("run_code", tools.TOOLS)
        by_name = {item["function"]["name"]: item["function"] for item in tools.schemas()}
        self.assertIn("run_code", by_name)
        enum = by_name["run_code"]["parameters"]["properties"]["language"]["enum"]
        self.assertEqual(["python", "javascript", "js", "node"], enum)
        self.assertIn("run_code", remote_security.GATED_REMOTE_TOOLS)

    def test_coding_system_prompt_swaps_in(self) -> None:
        general = agent.system_prompt(
            [{"role": "user", "content": "write a function"}],
            model="huihui_ai/qwen3-abliterated:14b")
        coding = agent.system_prompt(
            [{"role": "user", "content": "write a function"}],
            model=agent.router.CODING_MODEL)
        self.assertIn("general-purpose desktop assistant", general)
        self.assertNotIn("Debug loop", general)
        self.assertIn("Debug loop", coding)
        self.assertIn("run_code", coding)
        self.assertNotIn("general-purpose desktop assistant", coding)


if __name__ == "__main__":
    unittest.main(verbosity=2)
