"""Plan backend that runs Claude Code headless on the operator's subscription.

``MODEL_GATEWAY_PLAN_BACKEND=claude_cli`` (or ``auto``) sends the planning
request through ``claude -p`` instead of the Anthropic API, so the plan is
written by the operator's Claude subscription login rather than billed to an
API key. It is the same plan-only call as the API path:

* the prompt goes in on stdin, the answer comes back as one JSON result
  (``--output-format json``)
* every tool is switched off (``--tools ""``), the built-in tool names are
  denied as well (``--disallowedTools``), and anything still asking for
  permission is refused without a prompt (``--permission-mode dontAsk``)
* no MCP servers (``--strict-mcp-config`` with no ``--mcp-config``), no
  skills / slash commands, no saved session (``--no-session-persistence``)
* Claude Code's own coding-agent system prompt is replaced by the planning
  system prompt (``--system-prompt``)
* the working directory is a fresh temp directory, never the repository
* every ``ANTHROPIC_*`` variable is removed from the child environment, so an
  API key loaded from ``model_gateway/.env`` cannot switch the CLI to API
  billing and a local ``ANTHROPIC_BASE_URL`` cannot redirect it;
  ``DISABLE_AUTOUPDATER=1`` keeps a background plan call from updating Claude
  Code
* a hard timeout (``MODEL_GATEWAY_CLAUDE_CLI_TIMEOUT_S``)

Failures raise ``CloudUnavailable`` like the API adapter; ``planning.py``
turns that into a fallback (``auto``) or ``None``.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .config import GatewayConfig
from .events import CloudUnavailable, Completion

# Belt and braces next to --tools "": Claude Code's built-in tool names.
DENIED_TOOLS = ("Bash,BashOutput,KillShell,Edit,MultiEdit,Write,NotebookEdit,Read,Glob,Grep,"
                "LS,WebFetch,WebSearch,Task,Agent,TodoWrite,SlashCommand,Skill,ExitPlanMode")
STRIPPED_ENV_PREFIXES = ("ANTHROPIC_",)
_AUTH_HINTS = ("not logged in", "please run /login", "/login", "invalid api key",
               "authentication", "unauthorized", "oauth", "credit balance")


def build_command(exe: str, *, model: str, system_prompt: str, effort: str | None = None) -> list[str]:
    """argv for one headless, tool-less planning call. The prompt goes on stdin."""
    cmd = [exe, "-p",
           "--output-format", "json",
           "--model", model,
           "--tools", "",
           "--disallowedTools", DENIED_TOOLS,
           "--permission-mode", "dontAsk",
           "--strict-mcp-config",
           "--disable-slash-commands",
           "--no-session-persistence",
           "--system-prompt", system_prompt]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def child_env(environ: dict | None = None) -> dict:
    """Copy of the environment with every ``ANTHROPIC_*`` variable removed."""
    src = os.environ if environ is None else environ
    env = {k: v for k, v in src.items()
           if not any(k.upper().startswith(p) for p in STRIPPED_ENV_PREFIXES)}
    env["DISABLE_AUTOUPDATER"] = "1"
    return env


def _parse_result(stdout: str) -> dict | None:
    text = (stdout or "").strip()
    if not text:
        return None
    candidates = [text] + [line for line in reversed(text.splitlines()) if line.strip()]
    for chunk in candidates:
        try:
            data = json.loads(chunk)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _classify(message: str) -> str:
    low = (message or "").lower()
    return "auth" if any(h in low for h in _AUTH_HINTS) else "server"


def run_plan(cfg: GatewayConfig, system_prompt: str, user_text: str, *,
             runner=subprocess.run, environ: dict | None = None) -> Completion:
    """One ``claude -p`` call. Returns a ``Completion``; raises ``CloudUnavailable``."""
    exe = cfg.claude_cli
    if not exe:
        raise CloudUnavailable("disabled", "claude CLI not found (set MODEL_GATEWAY_CLAUDE_CLI)")
    cmd = build_command(exe, model=cfg.claude_cli_model, system_prompt=system_prompt,
                        effort=cfg.plan.effort)
    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    tmp = tempfile.TemporaryDirectory(prefix="model_gateway_plan_")
    try:
        try:
            proc = runner(cmd, input=user_text, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=tmp.name,
                          env=child_env(environ), timeout=cfg.claude_cli_timeout_s, **kwargs)
        except subprocess.TimeoutExpired:
            raise CloudUnavailable("timeout", f"claude CLI exceeded {cfg.claude_cli_timeout_s:.0f}s")
        except OSError as exc:
            raise CloudUnavailable("offline", f"claude CLI could not start: {type(exc).__name__}")
    finally:
        try:
            tmp.cleanup()
        except OSError:
            pass
    data = _parse_result(getattr(proc, "stdout", "") or "")
    stderr = (getattr(proc, "stderr", "") or "").strip()
    if data is None:
        msg = stderr or (getattr(proc, "stdout", "") or "").strip() or "no output"
        raise CloudUnavailable(_classify(msg),
                               f"claude CLI exit {proc.returncode}: {msg[:200]}")
    result_text = str(data.get("result") or "")
    if proc.returncode != 0 or data.get("is_error") or data.get("subtype") not in (None, "success"):
        msg = result_text or stderr or str(data.get("subtype") or "error")
        raise CloudUnavailable(_classify(msg),
                               f"claude CLI exit {proc.returncode} ({data.get('subtype')}): {msg[:200]}")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    model_usage = data.get("modelUsage") if isinstance(data.get("modelUsage"), dict) else {}
    model = next(iter(model_usage), None) or cfg.claude_cli_model
    telemetry = {"gateway": {
        "backend": "claude_cli",
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "duration_ms": data.get("duration_ms"),
        "num_turns": data.get("num_turns"),
    }}
    return Completion(model=str(model), text=result_text, calls=[],
                      stop_reason=str(data.get("stop_reason") or data.get("subtype") or "") or None,
                      telemetry=telemetry)
