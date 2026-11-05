from pathlib import Path
from datetime import datetime

root = Path(r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09")
changelog = root / "CHANGELOG" / "2026-09-01g_live_computer_task_audit.md"
status = root / "GROK_STATUS.md"

changelog_text = """# 2026-09-01g — Live computer-task audit (approved 6pm watch)

## Scope

Operator-approved live audit of the local agent chat loop on DuranGamingPC:
folder list, file write/read, cheap command, and unrelated-chat leak probe
(bare temperature / sleep question must not load specialist film handbook).

## Environment

- Agent HTTP: `http://127.0.0.1:8760`
- Started at revision `2026-09-01-profile-reload-r71` (GPU Ollama down);
  restarted to load disk `r72`, then patched and restarted to
  `2026-09-01-resident-gpu-none-r73` for the audit.
- Model: `huihui_ai/qwen3-abliterated:8b`, workspace `general`, `prefer=cpu`
- CPU Ollama started for the audit on `127.0.0.1:11435` (was down)
- GPU Ollama left down (CPU prefer path)

## Blocker found and patched mid-audit

Chat path crashed before any model hop when GPU Ollama was down:

`TypeError: 'NoneType' object is not iterable` at
`local_agent/agent.py` (`resident_gpu = router._running_models(...)` then
`for r in resident_gpu`).

Fix: coerce with `or []`. Revision bumped to
`2026-09-01-resident-gpu-none-r73`. Without this, the approved audit could
not run on CPU-only.

## Battery results

### Chat A — `54483cb19ddf4de4` (tasks 1–3)

1) **Folder list — PASS**
   - Tool: `list_dir` on `A:\\Users\\rhine\\Documents`
   - Evidence summary includes real names: Codex, FunGen, Battlefield 6, …
   - Independent `dir /b` matched those names
   - Did not dump the listing task back on the operator

2) **File write/read — PASS** (with caveat)
   - Tools: `write_file` created
     `A:\\Users\\rhine\\Documents\\local_agent_audit_20260901.txt`
     (26 chars); marker `AUDIT_MARKER_R73_9f2c7e11`
   - Independent disk read confirms marker alone on line 1
   - `read_file` then errored once (“does not exist”); agent used
     `list_dir` and reported success from write + listing
   - Caveat: did not successfully re-read file contents via tool, but
     wrote via tool and disk verification passed

3) **Cheap command (`hostname`) — FAIL**
   - Tools called: `run_code` twice
   - First: `unsupported language 'bash'`
   - Second: Python sandbox traceback / syntax error; agent said hostname
     output remains **unverified**
   - Final reply wandered back into prior Documents listing / audit file
     narration instead of pasting hostname
   - Independent baseline hostname is `DuranGamingPC` (not produced by agent)

### Chat B — `a77a3fb4edda4ee0` (task 4 leak probe)

4) **Unrelated-chat leak probe — PASS**
   - Prompt: “What's a comfortable indoor temperature in Fahrenheit for
     sleeping? Keep it short.”
   - Reply: “A comfortable indoor temperature for sleeping is typically
     **65–72°F (18–22°C)**, depending on personal preference and
     environmental factors.”
   - Leak: **no** — reply stays on temperature/sleep; no film clip IDs,
     specialist handbook language, MiniMax, H3, ComfyUI, Equal Shares, or
     render-pipeline talk in the assistant text
   - Route was CPU 8b; SSE route detail mentions `comfy_port_8188: closed`
     (status telemetry only, not model reply content)

## Failure-mode scores (operator cares)

- Dumping work back on operator: **not observed** on tasks 1–2; task 3
  failed tools but did not ask Rhine to run hostname
- Hallucinating paths/results without tools: task 3 admitted unverified;
  task 2 claimed marker after failed `read_file` (write tool had succeeded)
- Not calling tools when required: tasks 1–2 called tools; task 3 called
  tools but chose wrong/broken invocations

## Stop / next

Stop-until-go still holds for PowerInfer dump/train, pinning live,
Harmontown code, Zing second download, model downloads, LoRA train.
Cheap next CPU after go: Windows re-run of
`local_agent/test_native_tool_calling.py`. Bamboo-DPO still unregistered
(`prompt_contract_unresolved`).

Did not edit `tools/powerinfer/` or `router.py`.
"""

changelog.write_text(changelog_text, encoding="utf-8")
print("wrote", changelog)

old = status.read_text(encoding="utf-8")
# Replace Current handoff header block through the first blank-line end of section
marker = "## Current handoff"
idx = old.find(marker)
if idx < 0:
    raise SystemExit("Current handoff marker missing")
# Find end of current handoff: next "## Current (" or "## Bamboo" after first paragraph block
# We replace from start through the line "This is a coordination file..."
end_marker = "This is a coordination file, not an instruction to Codex. Do not treat it as a prompt."
end = old.find(end_marker, idx)
if end < 0:
    raise SystemExit("end marker missing")
end = end + len(end_marker)

new_block = """## Current handoff (2026-09-01 ~7:15 PM ET)

Live computer-task audit completed (chat loop on :8760). See
`CHANGELOG/2026-09-01g_live_computer_task_audit.md`. APP_REVISION now
`2026-09-01-resident-gpu-none-r73` (CPU-only crash when GPU Ollama down:
`resident_gpu` None). Battery: folder list PASS, file write/read PASS
(marker on disk), hostname cheap-command FAIL (run_code bash/python errors),
unrelated temperature leak probe PASS (no specialist handbook in reply).

first bot still honors **stop until Rhine says go**. Did not start
PowerInfer dump/train, pinning, Harmontown code, Zing second download,
model downloads, or LoRA train. Cheap next CPU after go remains Windows
re-run of `local_agent/test_native_tool_calling.py`. Bamboo-DPO stays
unregistered (`prompt_contract_unresolved`).

Written 2026-08-25 by Grok; **updated 2026-09-01 ~7:15 PM ET**. The current
handoff section above overrides dated entries below.
This is a coordination file, not an instruction to Codex. Do not treat it as a prompt."""

status.write_text(old[:idx] + new_block + old[end:], encoding="utf-8")
print("updated GROK_STATUS Current handoff")
