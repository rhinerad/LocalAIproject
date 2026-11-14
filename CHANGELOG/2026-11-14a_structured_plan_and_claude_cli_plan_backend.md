# 2026-11-14a — structured plan ("schematic") and a Claude Code subscription plan backend

Operator request (2026-11-14): when the local agent gets a hard task, have
Claude produce an exact plan and schematic that the local agent then
executes, and allow that plan to come from the operator's Claude
subscription rather than the API key. The request to drive the Claude
*desktop app* with an undetectable scraper was declined; this entry is the
sanctioned route to the same result. Branch `claude/jolly-dirac-9impbq`, on
top of `6bf7b69`. Id claimed with `scripts/next_changelog_id.py`. The product
rule is unchanged: Claude only writes the plan, the local Ollama model
executes every turn, and Claude never receives a tool.

## 1. Cause

- The plan was free text ("Return a numbered step-by-step plan ..."), so
  the local model got prose with no fixed place for files, commands, checks
  or stop conditions, and nothing could check what came back.
- The only plan backend was the Anthropic API, billed per token through
  `ANTHROPIC_API_KEY`. The operator also has a Claude subscription, and
  Claude Code 2.1.126 is installed on the workstation
  (`A:\Users\rhine\.local\bin\claude.exe`). It can run headless (`claude -p`)
  on that subscription login.

## 2. Change

Feature 1, structured plan (`model_gateway/planning.py`):

- `SYSTEM_TEMPLATE` now asks for exactly one JSON object: `goal`,
  `assumptions`, `steps[]` (`id`, `action`, `files_read`, `files_change`,
  `commands`, `tools`, `expected`, `verify`), `acceptance` and `stop_if`. It
  still names the local tools and still says "Do not perform the task".
- `parse_plan(text, tool_names)` accepts the object bare, fenced or wrapped
  in prose. It also takes a few alias keys, renumbers steps 1..n, and keeps
  only tool names the local agent has (others go under `dropped_tools`).
  `render_plan()` turns the plan into a numbered checklist: Read / Change /
  Tools / Run / Expect / Verify for each step, then "Done when" and "Stop and
  report instead of guessing if".
- `request_plan()` keeps its contract (text or `None`, never raises). It now
  returns `PlanText`, a `str` subclass holding the rendered checklist, or
  the raw text when the reply is not a valid plan object, so a plan is never
  lost. Its attributes are `.plan_format` (`structured`/`text`),
  `.structured`, `.raw`, `.backend` and `.model`. The new
  `request_structured_plan()` returns just the dict.
- `MODEL_GATEWAY_PLAN_MAX_TOKENS` default goes from 1500 to 3000 (still
  configurable and clamped to 256..8000), because the JSON form is longer.
  The workstation `.env` does not set this key, so the new default applies
  there.
- `local_agent/agent.py` `_request_cloud_plan()` uses a checklist header
  for structured plans. It records `detail.plan_format`
  (`structured`/`text`/`none`) and `detail.plan_backend`
  (`api`/`claude_cli`/`none`) next to the existing `plan_source`. The note
  text "cloud plan received" is unchanged.
- `dispatch.note_plan()` records `backend` and `plan_format` in `last_plan`.

Feature 2, Claude Code CLI backend (new `model_gateway/claude_cli.py`;
`config.py`, `policy.py`):

- `MODEL_GATEWAY_PLAN_BACKEND=api|claude_cli|auto`. The default is `api`,
  so behaviour does not change until the operator flips it. `auto` tries the
  CLI first and falls back to the API on any CLI failure. `claude_cli`
  returns `None` on failure, and the turn continues locally as before.
  `MODEL_GATEWAY_CLOUD=1` is still the master switch for every backend.
  `claude_cli` needs no API key.
- Optional settings: `MODEL_GATEWAY_CLAUDE_CLI` (path; default
  `%USERPROFILE%\.local\bin\claude.exe`, then PATH, preferring the native
  `.exe` over the npm `.cmd` shim, which would mangle the empty `--tools ""`
  argument through cmd.exe), `MODEL_GATEWAY_CLAUDE_CLI_MODEL` (default
  `opus`) and `MODEL_GATEWAY_CLAUDE_CLI_TIMEOUT_S` (default 300). The CLI is
  only looked up when the backend is not `api`.
- The command, every flag checked against `claude --help` on the
  workstation (2.1.126), with the prompt on stdin:
  `claude -p --output-format json --model opus --tools "" --disallowedTools
  Bash,...,Read,...,WebFetch,... --permission-mode dontAsk
  --strict-mcp-config --disable-slash-commands --no-session-persistence
  --system-prompt <planning prompt> --effort <MODEL_GATEWAY_PLAN_EFFORT>`.
- The working directory is a fresh temp directory, never the repo. Every
  `ANTHROPIC_*` variable is removed from the child environment, because
  `load_config()` copies `ANTHROPIC_API_KEY` from `.env` into the gateway
  process and the CLI would otherwise bill that key.
  `DISABLE_AUTOUPDATER=1` is set so a background plan call never updates
  Claude Code. `--bare` was not used: it forces API-key auth.
- `GatewayConfig` gains `plan_backend`, `claude_cli`, `claude_cli_model`,
  `claude_cli_timeout_s`, `api_available` and `cli_available`.
  `planning_available` means: cloud on, and the selected backend is usable.
  `wants_cloud_plan` gives a backend-specific reason; for `api` the old
  message is unchanged. `public_dict()` reports the backend and whether the
  CLI was found, never a path to a credential and never a key.
- Docs: `model_gateway/README.md` has a "Plan backend" section and the plan
  format; `env.example` documents the switch with no secrets;
  `__init__.py` exports the new names.

Tests: new `model_gateway/test_planning.py` (20, offline: a stub API object
and a fake `subprocess.run`, no network and no real CLI). It covers
structured parsing, fenced JSON, malformed input falling back to text, tool
filtering, CLI argv with tools disabled, no `ANTHROPIC_*` in the child env,
a temp cwd, CLI timeout / not signed in / error falling back to the API in
`auto` and returning `None` in `claude_cli`, and `api` as the default that
never runs the CLI. `test_router_hooks.py` gains 2 tests (`plan_format` /
`plan_backend` in the route detail; the structured header and rendered
checklist injected). The `max_tokens` expectation in `test_policy.py` and
`test_adapter_mock.py` moves from 1500 to 3000.

## 3. Evidence (workstation, gateway worktree, override `EQUAL_SHARES_PRIMARY_REASONING_MODEL` unchanged)

    local_agent\test_capability_routing.py      Ran 44 tests   OK
    local_agent\test_router_comfy_timeshare.py  Ran 51 tests   OK
    local_agent\test_router_switching.py        Ran 54 tests   OK
    local_agent\test_router_status_busy.py      Ran 8 tests    OK
    local_agent\test_gpu_vram_num_ctx.py        Ran 7 tests    OK
    local_agent\test_native_tool_calling.py     Ran 118 tests  OK
    model_gateway\test_policy.py                Ran 14 tests   OK
    model_gateway\test_adapter_mock.py          Ran 16 tests   OK
    model_gateway\test_router_hooks.py          Ran 20 tests   OK   (was 18)
    model_gateway\test_translate.py             Ran 16 tests   OK
    model_gateway\test_planning.py              Ran 20 tests   OK   (new)

`claude auth status`: `loggedIn=true`, `authMethod=claude.ai`,
`subscriptionType=max` (only these fields were read). There was one live
smoke test through `planning.request_plan` with
`MODEL_GATEWAY_PLAN_BACKEND=claude_cli`, read_env_file off (no API key in the
process), the prompt "Plan how to add a docstring to the function parse_args
in cli.py." and tools `read_file, write_file, run_tests`. It returned
`plan_format=structured`, `backend=claude_cli`, model `claude-opus-4-7` (what
the CLI's `opus` alias resolved to), 3 steps, no dropped tools, raw 1801
chars, rendered 1665 chars, 9.1 s, `num_turns=1`, 855 tokens in / 656 out,
and stop `end_turn`. Every step had Read/Change/Tools/Run/Expect/Verify
filled in. No GUI, render, ComfyUI or Ollama model load was involved.

## 4. Unverified / next

- Not exercised in a GUI turn. The agent-side change is covered by
  `test_router_hooks.py` only.
- The API backend was not called live with the new JSON prompt; the API
  path is covered by the mock tests.
- The CLI's `opus` alias resolves to Claude Code's current Opus
  (`claude-opus-4-7` on 2026-11-14), not `MODEL_GATEWAY_PLAN_MODEL`
  (`claude-opus-5-5`). Set `MODEL_GATEWAY_CLAUDE_CLI_MODEL` to a full model
  name to pin it.
- The workstation `.env` still carries keys from the first prototype
  (`MODEL_GATEWAY_FAST_*`, `MODEL_GATEWAY_MAX_TOKENS`,
  `MODEL_GATEWAY_BUSY_TIER`) that nothing reads. They are harmless, and
  this entry left them alone.
- To switch on: add `MODEL_GATEWAY_PLAN_BACKEND=claude_cli` (or `auto`) to
  `model_gateway\.env` and restart the agent.
