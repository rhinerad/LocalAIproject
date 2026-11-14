"""Offline tests for the structured plan and the Claude Code CLI plan backend.

No network and no real ``claude``: the API backend is a stub object and the
CLI is replaced by a fake ``subprocess.run`` that records its arguments.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from model_gateway import claude_cli, dispatch, planning  # noqa: E402
from model_gateway import config as cfgmod  # noqa: E402
from model_gateway import policy  # noqa: E402
from model_gateway.events import CloudUnavailable, Completion  # noqa: E402

TOOLS = ["read_file", "list_dir", "run_tests"]

GOOD_PLAN = {
    "goal": "Add a docstring to parse_args",
    "assumptions": ["parse_args lives in cli.py"],
    "steps": [
        {"id": 1, "action": "Open cli.py and find parse_args", "files_read": ["cli.py"],
         "files_change": [], "commands": [], "tools": ["read_file"],
         "expected": "function located", "verify": "line number of def parse_args noted"},
        {"id": 2, "action": "Write the docstring", "files_read": [], "files_change": ["cli.py"],
         "commands": ["python -m pytest tests/test_cli.py"], "tools": ["run_tests", "Bash"],
         "expected": "docstring present", "verify": "tests pass"},
    ],
    "acceptance": ["parse_args has a docstring", "tests still pass"],
    "stop_if": ["cli.py does not exist"],
}


def make_cfg(**env):
    base = {"MODEL_GATEWAY_CLOUD": "1", "ANTHROPIC_API_KEY": "sk-test-secret"}
    base.update(env)
    return cfgmod.load_config(base, read_env_file=False)


class StubApi:
    def __init__(self, text="1. plain step", exc=None):
        self.text, self.exc, self.calls = text, exc, []

    def complete(self, **kw):
        self.calls.append(kw)
        if self.exc:
            raise self.exc
        return Completion(model="claude-opus-5-5", text=self.text, stop_reason="end_turn")


class FakeRun:
    """Stands in for subprocess.run; records argv/env/cwd."""

    def __init__(self, stdout="", returncode=0, stderr="", exc=None):
        self.stdout, self.returncode, self.stderr, self.exc = stdout, returncode, stderr, exc
        self.calls = []

    def __call__(self, cmd, **kw):
        self.calls.append({"cmd": list(cmd), **kw})
        if self.exc:
            raise self.exc
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)


def cli_json(result, is_error=False, subtype="success"):
    return json.dumps({"type": "result", "subtype": subtype, "is_error": is_error,
                       "result": result, "duration_ms": 1200, "num_turns": 1,
                       "usage": {"input_tokens": 50, "output_tokens": 120},
                       "modelUsage": {"claude-opus-test": {}}})


class StructuredPlanTests(unittest.TestCase):
    def test_parse_success_and_render(self):
        plan = planning.parse_plan(json.dumps(GOOD_PLAN), TOOLS)
        self.assertIsNotNone(plan)
        self.assertEqual("Add a docstring to parse_args", plan["goal"])
        self.assertEqual([1, 2], [s["id"] for s in plan["steps"]])
        self.assertEqual(["python -m pytest tests/test_cli.py"], plan["steps"][1]["commands"])
        text = planning.render_plan(plan)
        self.assertIn("Goal: Add a docstring to parse_args", text)
        self.assertIn("1. Open cli.py and find parse_args", text)
        self.assertIn("   Run: python -m pytest tests/test_cli.py", text)
        self.assertIn("   Verify: tests pass", text)
        self.assertIn("Done when:", text)
        self.assertIn("Stop and report instead of guessing if:", text)

    def test_tool_names_are_filtered(self):
        plan = planning.parse_plan(json.dumps(GOOD_PLAN), TOOLS)
        self.assertEqual(["run_tests"], plan["steps"][1]["tools"])
        self.assertEqual(["Bash"], plan["dropped_tools"])
        none = planning.parse_plan(json.dumps(GOOD_PLAN), [])
        self.assertEqual([], none["steps"][0]["tools"])

    def test_fenced_json_with_prose(self):
        text = "Here is the plan:\n```json\n" + json.dumps(GOOD_PLAN, indent=2) + "\n```\nGood luck."
        plan = planning.parse_plan(text, TOOLS)
        self.assertIsNotNone(plan)
        self.assertEqual(2, len(plan["steps"]))

    def test_renumbers_and_accepts_aliases(self):
        raw = {"objective": "x", "steps": [{"id": 7, "description": "first", "check": "ok"},
                                           "second as a string", {"id": 9}],
               "acceptance_criteria": "all good", "stop_conditions": ["broken"]}
        plan = planning.parse_plan(json.dumps(raw), TOOLS)
        self.assertEqual([(1, "first"), (2, "second as a string")],
                         [(s["id"], s["action"]) for s in plan["steps"]])
        self.assertEqual("ok", plan["steps"][0]["verify"])
        self.assertEqual(["all good"], plan["acceptance"])
        self.assertEqual(["broken"], plan["stop_if"])

    def test_malformed_falls_back_to_text(self):
        for bad in ('{"goal": "x", "steps": [', "1. read\n2. edit", '{"goal": "no steps"}',
                    '{"steps": []}', ""):
            with self.subTest(bad=bad):
                self.assertIsNone(planning.parse_plan(bad, TOOLS))
        pt = planning.to_plan_text('{"goal": "x", "steps": [', TOOLS)
        self.assertEqual("text", pt.plan_format)
        self.assertEqual('{"goal": "x", "steps": [', str(pt))   # never lose a plan
        self.assertIsNone(pt.structured)

    def test_system_prompt_asks_for_json_and_lists_tools(self):
        system, msgs = planning.build_plan_messages("do it", "", TOOLS)
        self.assertIn("read_file, list_dir, run_tests", system)
        self.assertIn("Do not perform the task", system)
        self.assertIn('"steps"', system)
        self.assertIn('"verify"', system)
        self.assertIn('"stop_if"', system)
        self.assertEqual("system", msgs[0]["role"])


class RequestPlanTests(unittest.TestCase):
    def test_api_structured_plan(self):
        api = StubApi(text="```json\n" + json.dumps(GOOD_PLAN) + "\n```")
        plan = planning.request_plan("Add a docstring", "", TOOLS, config=make_cfg(), backend=api)
        self.assertIsInstance(plan, str)
        self.assertEqual("structured", plan.plan_format)
        self.assertEqual("api", plan.backend)
        self.assertIn("1. Open cli.py", plan)
        self.assertIn("```json", plan.raw)
        self.assertIsNone(api.calls[0]["tools"])
        self.assertEqual(3000, api.calls[0]["options"]["max_tokens"])
        self.assertEqual("structured", dispatch.status_snapshot(make_cfg())["last_plan"]["plan_format"])

    def test_api_text_plan_unchanged(self):
        plan = planning.request_plan("x", config=make_cfg(), backend=StubApi("1. a\n2. b"))
        self.assertEqual("1. a\n2. b", plan)
        self.assertEqual("text", plan.plan_format)

    def test_request_structured_plan(self):
        api = StubApi(text=json.dumps(GOOD_PLAN))
        plan = planning.request_structured_plan("x", "", TOOLS, config=make_cfg(), backend=api)
        self.assertEqual(2, len(plan["steps"]))
        self.assertIsNone(planning.request_structured_plan(
            "x", config=make_cfg(), backend=StubApi("1. text")))

    def test_default_backend_is_api_and_never_runs_cli(self):
        cfg = make_cfg()
        self.assertEqual("api", cfg.plan_backend)
        run = FakeRun(stdout=cli_json("1. cli"))
        plan = planning.request_plan("x", config=cfg, backend=StubApi("1. api"), cli_runner=run)
        self.assertEqual("api", plan.backend)
        self.assertEqual([], run.calls)

    def test_claude_cli_backend(self):
        cfg = make_cfg(MODEL_GATEWAY_PLAN_BACKEND="claude_cli",
                       MODEL_GATEWAY_CLAUDE_CLI=sys.executable)
        run = FakeRun(stdout=cli_json(json.dumps(GOOD_PLAN)))
        api = StubApi("1. api")
        plan = planning.request_plan("Add a docstring", "", TOOLS, config=cfg, backend=api,
                                     cli_runner=run)
        self.assertEqual("claude_cli", plan.backend)
        self.assertEqual("structured", plan.plan_format)
        self.assertEqual([], api.calls)
        self.assertIn("Operator request:\nAdd a docstring", run.calls[0]["input"])

    def test_cli_failure_falls_back_to_api_in_auto(self):
        cfg = make_cfg(MODEL_GATEWAY_PLAN_BACKEND="auto", MODEL_GATEWAY_CLAUDE_CLI=sys.executable)
        for run in (FakeRun(exc=subprocess.TimeoutExpired("claude", 300)),
                    FakeRun(stdout=cli_json("Not logged in · Please run /login", is_error=True),
                            returncode=1),
                    FakeRun(stdout="", returncode=1, stderr="boom")):
            with self.subTest(run=run):
                api = StubApi("1. from api")
                plan = planning.request_plan("x", config=cfg, backend=api, cli_runner=run)
                self.assertEqual("1. from api", plan)
                self.assertEqual("api", plan.backend)
                self.assertEqual(1, len(run.calls))
                self.assertEqual(1, len(api.calls))

    def test_cli_failure_returns_none_in_claude_cli_mode(self):
        cfg = make_cfg(MODEL_GATEWAY_PLAN_BACKEND="claude_cli",
                       MODEL_GATEWAY_CLAUDE_CLI=sys.executable)
        api = StubApi("1. api")
        run = FakeRun(exc=subprocess.TimeoutExpired("claude", 300))
        self.assertIsNone(planning.request_plan("x", config=cfg, backend=api, cli_runner=run))
        self.assertEqual([], api.calls)
        self.assertEqual("timeout", dispatch.status_snapshot(cfg)["last_fallback"]["kind"])
        auth = FakeRun(stdout=cli_json("Not logged in · Please run /login", is_error=True),
                       returncode=1)
        self.assertIsNone(planning.request_plan("x", config=cfg, backend=api, cli_runner=auth))
        self.assertEqual("auth", dispatch.status_snapshot(cfg)["last_fallback"]["kind"])
        self.assertIsNone(planning.request_plan(
            "x", config=cfg, cli_runner=FakeRun(exc=FileNotFoundError("claude"))))

    def test_api_failure_never_raises(self):
        plan = planning.request_plan("x", config=make_cfg(),
                                     backend=StubApi(exc=RuntimeError("boom")))
        self.assertIsNone(plan)
        plan = planning.request_plan("x", config=make_cfg(),
                                     backend=StubApi(exc=CloudUnavailable("offline", "down")))
        self.assertIsNone(plan)


class ClaudeCliBackendTests(unittest.TestCase):
    def cfg(self, **env):
        return make_cfg(MODEL_GATEWAY_PLAN_BACKEND="claude_cli",
                        MODEL_GATEWAY_CLAUDE_CLI=sys.executable, **env)

    def test_command_line_disables_tools(self):
        run = FakeRun(stdout=cli_json("1. step"))
        claude_cli.run_plan(self.cfg(), "SYSTEM TEXT", "user text", runner=run,
                            environ={"PATH": "x"})
        cmd = run.calls[0]["cmd"]
        self.assertEqual(sys.executable, cmd[0])
        self.assertIn("-p", cmd)
        self.assertEqual("json", cmd[cmd.index("--output-format") + 1])
        self.assertEqual("opus", cmd[cmd.index("--model") + 1])
        self.assertEqual("", cmd[cmd.index("--tools") + 1])          # all tools off
        denied = cmd[cmd.index("--disallowedTools") + 1].split(",")
        for name in ("Bash", "Edit", "Write", "Read", "WebFetch", "Task"):
            self.assertIn(name, denied)
        self.assertEqual("dontAsk", cmd[cmd.index("--permission-mode") + 1])
        for flag in ("--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"):
            self.assertIn(flag, cmd)
        self.assertNotIn("--mcp-config", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertNotIn("--add-dir", cmd)
        self.assertEqual("SYSTEM TEXT", cmd[cmd.index("--system-prompt") + 1])
        self.assertEqual("high", cmd[cmd.index("--effort") + 1])
        self.assertNotIn("user text", cmd)                           # prompt goes on stdin
        self.assertEqual("user text", run.calls[0]["input"])

    def test_child_env_has_no_api_key_and_cwd_is_temp(self):
        run = FakeRun(stdout=cli_json("1. step"))
        environ = {"PATH": "p", "ANTHROPIC_API_KEY": "sk-secret", "ANTHROPIC_AUTH_TOKEN": "t",
                   "ANTHROPIC_BASE_URL": "http://127.0.0.1:11435",
                   "EQUAL_SHARES_PRIMARY_REASONING_MODEL": "keep-me"}
        claude_cli.run_plan(self.cfg(), "s", "u", runner=run, environ=environ)
        env = run.calls[0]["env"]
        self.assertFalse([k for k in env if k.upper().startswith("ANTHROPIC_")])
        self.assertNotIn("sk-secret", json.dumps(env))
        self.assertEqual("keep-me", env["EQUAL_SHARES_PRIMARY_REASONING_MODEL"])
        self.assertEqual("1", env["DISABLE_AUTOUPDATER"])
        self.assertIn("sk-secret", environ.values())                 # caller env untouched
        cwd = Path(run.calls[0]["cwd"]).resolve()
        repo = Path(__file__).resolve().parents[1]
        self.assertTrue(str(cwd).startswith(str(Path(tempfile.gettempdir()).resolve())))
        self.assertNotEqual(repo, cwd)
        self.assertNotIn(str(repo), str(cwd))
        self.assertEqual(self.cfg().claude_cli_timeout_s, run.calls[0]["timeout"])
        self.assertNotIn("sk-test-secret", json.dumps(run.calls[0]["cmd"]))

    def test_result_parsing_and_errors(self):
        out = claude_cli.run_plan(self.cfg(), "s", "u", runner=FakeRun(stdout=cli_json("plan!")))
        self.assertEqual("plan!", out.text)
        self.assertEqual("claude-opus-test", out.model)
        self.assertEqual([], out.calls)
        self.assertEqual("claude_cli", out.telemetry["gateway"]["backend"])
        with self.assertRaises(CloudUnavailable) as ctx:
            claude_cli.run_plan(self.cfg(), "s", "u",
                                runner=FakeRun(exc=subprocess.TimeoutExpired("claude", 1)))
        self.assertEqual("timeout", ctx.exception.kind)
        with self.assertRaises(CloudUnavailable) as ctx:
            claude_cli.run_plan(self.cfg(), "s", "u",
                                runner=FakeRun(stdout=cli_json("x", subtype="error_max_turns")))
        self.assertEqual("server", ctx.exception.kind)
        no_cli = cfgmod.GatewayConfig(**{**self.cfg().__dict__, "claude_cli": ""})
        with self.assertRaises(CloudUnavailable) as ctx:
            claude_cli.run_plan(no_cli, "s", "u", runner=FakeRun())
        self.assertEqual("disabled", ctx.exception.kind)


class BackendConfigTests(unittest.TestCase):
    def test_backend_values(self):
        self.assertEqual("api", make_cfg().plan_backend)
        self.assertEqual("api", make_cfg(MODEL_GATEWAY_PLAN_BACKEND="bogus").plan_backend)
        self.assertEqual("claude_cli", make_cfg(MODEL_GATEWAY_PLAN_BACKEND="cli").plan_backend)
        self.assertEqual("auto", make_cfg(MODEL_GATEWAY_PLAN_BACKEND="AUTO").plan_backend)

    def test_cli_backend_needs_no_api_key_but_needs_master_switch(self):
        env = {"MODEL_GATEWAY_PLAN_BACKEND": "claude_cli", "MODEL_GATEWAY_CLAUDE_CLI": sys.executable}
        on = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1", **env}, read_env_file=False)
        self.assertTrue(on.planning_available)
        self.assertFalse(on.credential_present)
        off = cfgmod.load_config(env, read_env_file=False)
        self.assertFalse(off.planning_available)
        missing = cfgmod.load_config({"MODEL_GATEWAY_CLOUD": "1",
                                      "MODEL_GATEWAY_PLAN_BACKEND": "claude_cli",
                                      "MODEL_GATEWAY_CLAUDE_CLI": os.path.join(
                                          tempfile.gettempdir(), "no-such-claude.exe")},
                                     read_env_file=False)
        self.assertFalse(missing.planning_available)
        wanted, why = policy.wants_cloud_plan(config=missing, prefer="auto", model=None,
                                              capability="logic", has_prompt=True)
        self.assertFalse(wanted)
        self.assertIn("claude CLI not found", why)

    def test_public_dict_reports_backend_without_secrets(self):
        d = make_cfg(MODEL_GATEWAY_PLAN_BACKEND="auto",
                     MODEL_GATEWAY_CLAUDE_CLI=sys.executable).public_dict()
        self.assertEqual("auto", d["plan_backend"])
        self.assertTrue(d["claude_cli_found"])
        self.assertNotIn("sk-test-secret", json.dumps(d))


if __name__ == "__main__":
    unittest.main()
