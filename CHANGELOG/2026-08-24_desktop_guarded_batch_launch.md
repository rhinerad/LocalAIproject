# 2026-08-24 — Desktop guarded batch-render launch

## What changed

- `local_agent/tools.py`: added `start_batch_render`, a fixed desktop-only
  launcher for `work/batch_render_folder.py`.
- `local_agent/agent.py`: routes an explicit desktop start request to that action.
- `local_agent/remote_security.py`: phone identities default-deny the new action.
- `local_agent/static/index.html`: corrected the capability statement.
- `CLAUDE.md`: records the narrowly scoped operator override of the former
  proposal-only local-agent rule.
- `local_agent/test_native_tool_calling.py`: added launch preflight and remote
  default-deny regressions.

## Why

The operator explicitly requires the desktop local agent to start a general
batch render, rather than merely print a terminal command. The previous GUI
correctly said that it could not start a render.

## Safety boundary

The action accepts no shell command. It launches only the checked-in batch
runner after all of these pass:

1. a real supplied job folder exists and is outside `outputs/equal_shares/**`;
2. the folder's read-only plan has at least one render and zero invalid prompts;
3. port 8188 and every recognized render owner are inactive;
4. no live batch-owner PID is present; and
5. `--force` is refused, so the agent has no overwrite path.

The existing runner still claims/releases its own queue lock, calls
`thermal_guard.py`, starts/stops only its own ComfyUI backend, and produces
unique output paths. Phone contexts remain default-deny and audited.

## Evidence and verification

`python local_agent\\test_native_tool_calling.py` passed **14/14**. The new
tests verified the exact fixed runner invocation with a mocked process (no
process launched) and refusal from a phone context. Schema parity reported
`32 32` (one schema per tool).

## Still unverified

No batch render was started. A real job-folder launch and its output metadata
still require an explicit operator-provided folder and later render audit.
