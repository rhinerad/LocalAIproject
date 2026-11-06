# Claude Code / Codex prompt — coding mode (Qwen2.5-Coder) + a safe run-and-test sandbox

Paste into your coding agent. Work in `COMFYUI_STORY_HANDOFF_2026-08-09/local_agent/`.
Read `router.py`, `agent.py`, `tools.py` (esp. `write_candidate_tool`,
`run_safe_check`, `write_file`/`read_file`, the `_TOOLS`/`_SCHEMAS` registry),
`server.py`, `static/index.html`, and `START_LOCAL_AGENT_GUI.ps1` first.
**Constraints:** stdlib only; server on `127.0.0.1`; `tools.py` stays a whitelist;
never start a render/ComfyUI; never touch `outputs/equal_shares/**` or project files
from the sandbox; phone identities stay default-denied for code execution.

## Goal

Make the local agent genuinely useful for writing and **debugging** programs, within
the 16 GB card. Two parts: (1) a **coding mode** that uses a code-specialist model and
a coding system prompt; (2) a **sandboxed run-and-test loop** so the model can execute
code, read the real error, and fix it — the thing that actually makes it debug.

## Part 1 — coding mode

- Add `CODING_MODEL = os.environ.get("EQUAL_SHARES_CODING_MODEL",
  "huihui_ai/qwen2.5-coder-abliterate:14b")` in `router.py`. It is already in the
  GPU/CPU fallback lists; make it explicitly selectable, not just a fallback.
- Ensure it's installed: extend `START_LOCAL_AGENT_GUI.ps1` to optionally ensure the
  coding model on the GPU server (same `Ensure-GpuChatModel` pattern, pulled only by the
  launcher, only if a flag/env asks for it — do not force a ~9 GB pull on every start).
- Expose "coding mode" in the GUI: the model picker already supports model-per-chat, so
  add a clear **Coding mode** choice that (a) selects `CODING_MODEL` and (b) swaps in a
  **coding system prompt** — concise, test-driven, "write the code, then run it in the
  sandbox and fix failures before answering", cite exact errors, no invented APIs, prefer
  stdlib, state assumptions. Keep the general assistant prompt for normal chats.
- Routing unchanged: coding mode still goes through `router` (GPU 14B-coder when the card
  is idle, CPU fallback when a render owns it). A 14B coder on CPU is slow — surface that
  in the UI so the operator knows to free the GPU for heavy coding.

## Part 2 — the sandbox (`run_code` tool)

Add a `run_code` tool to `tools.py` that executes code in an **isolated, bounded**
environment so the agent can iterate:

- **Isolation:** a dedicated dir `local_agent/sandbox/run_<id>/` (created per run). The
  sandbox may read/write only inside its own run dir. It must NOT see the project tree,
  `outputs/`, uploads, or any model/render file. Set the subprocess `cwd` to the run dir.
- **Interpreters:** start with Python (the repo's Python); optionally Node if `node` is on
  PATH. A fixed allowlist of interpreters — never an arbitrary shell string.
- **Bounds:** hard `timeout` (e.g. 30 s default, cap 120 s), capture stdout+stderr+exit
  code, cap captured output size. Kill the process group on timeout. Limit what one run
  can spawn.
- **No network by default:** run with a flag/env that disables network (and document that
  the guarantee is best-effort on Windows). A `allow_network:true` arg exists but is
  off by default and logged.
- **Input:** `{"language":"python","code":"...","stdin":"...","timeout":30}` OR
  `{"language":"python","path":"sandbox/run_x/main.py"}` to run a file the agent wrote
  there with `write_file`. Return `{stdout, stderr, exit_code, timed_out, duration}`.
- **Never** executes anything under the project tree; refuse a `path` outside the sandbox.
  Never runs while a render owns the GPU is NOT required (CPU code execution doesn't need
  the GPU) — but a `run_code` that itself tries to use the GPU is out of scope; keep it CPU.

Then wire the **debug loop** into coding mode's guidance: write file → `run_code` → read
stderr → edit → re-run, with a capped number of iterations per turn so it can't loop
forever. This is the core capability that makes local debugging work.

## Part 3 — keep the existing dev-workspace tools coherent

`write_candidate_tool` (isolated dev workspace, cannot run/replace project code) already
exists. `run_code` complements it: candidate helpers can be *tried* in the sandbox, but
still can never run against or replace project code. Make the boundary explicit in both
tool descriptions. `write_file`/`propose_file_diff` continue to gate protected project
files; the sandbox is the only place code actually executes.

## Security recap (do not weaken)

- The sandbox is the ONLY code-execution surface, and it is walled to its run dir, CPU,
  bounded time/output, network-off by default, no project/outputs/render access.
- `run_code` is **desktop-only** and **default-denied for phone/remote identities** (reuse
  the Sideband per-identity permission gate).
- Never delete project evidence; sandbox run dirs may be cleaned on a size/age policy, but
  nothing outside `local_agent/sandbox/` is ever touched.

## Verify (show commands + output)

- `python local_agent/test_native_tool_calling.py` still green (update the tool-count/enum
  test for the new `run_code` tool).
- New stdlib tests for `run_code`: a hello-world returns stdout + exit 0; an infinite loop
  hits the timeout and is killed (`timed_out:true`); a script that tries to read a project
  file OUTSIDE the run dir fails/refuses; a `path` outside `sandbox/` is refused; captured
  output is size-capped.
- Coding-mode routing test: coding mode selects `CODING_MODEL`; unknown coding model name
  falls back cleanly; CPU path used when a render owns the GPU.
- `validate_h3_prompt.py` still 124/124.

## Record it

`CHANGELOG/<today>_coding_mode_and_sandbox.md` — what changed, why, the test output, and
what's unverified (a live coding session with the 14B-coder on GPU needs a real model
load). Add coding mode + `run_code` + the sandbox boundary to `local_agent/README.md`,
and note in `BUILD_STATUS.md` that local coding capability now exists (coder model +
sandboxed debug loop), with the honest ceiling: strong local junior/mid coder, not
frontier — route hard multi-file work to a cloud model.
