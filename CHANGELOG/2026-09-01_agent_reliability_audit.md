# 2026-09-01 - Local agent reliability audit and exact-evidence recovery

## Why

The operator reported that the local agent repeatedly failed to finish a simple
PowerInfer calibration-file task. In the saved chat it had once discovered the
real file path, then later asked the operator for a path, used
`review-only/.../approved.jsonl`, gave instructions instead of acting, and made
claims that were not supported by tool evidence.

## Findings

- The main action and tool loop is present and mostly covered: native Ollama
  tool calls, multiple calls per hop, legacy fallback, action-request retry,
  current-chat render guard, batch-render current-turn guard, exact JSONL repair,
  prior-chat retrieval boundaries, tool-output pruning, GPU routing, media queue
  arbitration, and phone permission checks are all covered by local tests.
- The actual failing conversation exposed a lossy evidence format. `server.py`
  saved each `tool_result` as only a 240-character summary. Long Windows paths
  inside validator JSON were truncated, so a later restart/compaction could not
  parse the exact `powerinfer_project\approved_tasks.jsonl` path.
- The audit run also exposed a Windows race in `atomic_io.atomic_write_text`:
  two nearby writes could collide on the same sibling `.tmp` file name while
  updating tiny status markers such as `runtime/chat_busy.json`.
- The media sweep exposed a false-negative Whisper capability check. The local
  ComfyUI Whisper-tiny checkpoint is present, but the cold import of
  `torch, whisper, safetensors` can take longer than the previous 30-second
  cutoff.

## Changes

- `local_agent/server.py`
  - Tool receipts now keep structured fields from JSON tool results:
    `path`, `valid`, `reason`, `records`, `file_changed`, `repaired`, and
    `next_step`, in addition to the short visible summary.
  - Saved-chat evidence injected into a later request preserves those fields.
- `local_agent/agent.py`
  - Failed-calibration recovery now reads the structured receipt fields.
  - Older already-saved truncated receipts are scanned for exact `.jsonl` paths,
    while still rejecting ellipses/placeholders.
- `local_agent/atomic_io.py`
  - Atomic writes now use a unique sibling temp file and retry replacement
    briefly on `PermissionError`.
- `local_agent/capabilities.py`
  - The offline ComfyUI Whisper import probe timeout increased to 75 seconds.
- `local_agent/test_native_tool_calling.py`
  - Added regression coverage for recovering a calibration path from a truncated
    saved receipt matching the real failure class.
- `local_agent/README.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md`,
  and `docs/LOCAL_AGENT_REGRESSION_RUNBOOK.md`
  - Updated with the audit findings and current test counts.

## Verification

Run from the repository root unless noted:

```powershell
python local_agent\test_native_tool_calling.py
python local_agent\test_agentic_state.py
python local_agent\test_router_switching.py
python -m py_compile local_agent\server.py local_agent\agent.py local_agent\atomic_io.py
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
```

Results:

- Native/tool suite: 55 tests passed.
- Agentic task-state suite: 13 tests passed.
- Router suite: 42 tests passed.
- H3 prompt validation: 124/124 valid.
- Py-compile: passed.

Full documented local-agent sweep from `local_agent\`:

- Group 1: 29 tests passed.
- Group 2: 19 tests passed.
- Group 3: 46 tests passed.
- Group 4: 119 tests passed.
- Group 5: 39 tests passed, 2 skipped.
- Group 6: 48 tests passed.
- Group 7: 171 tests passed.
- Total: 471 bounded local-agent tests passed.

Worker-farm suite:

- 19 tests passed, 1 expected skip.

## Not done

No render, ComfyUI process, Sideband bridge, PowerInfer predictor generation,
model load, checkpoint edit, registry change, GPU workload, download, or worker
job was started. The audited PowerInfer JSONL remains an intake/configuration
artifact, not a render job and not authorization for model work.

## Remaining architectural risk

`agent.answer()` is still the central integration hotspot for routing, planning,
tool calls, context prefetch, GPU gating, and recovery. The new fixes harden the
observed failure class, but a future refactor should extract a durable
"action resolution" layer so new task types do not require one more regex or
special-case branch in the main loop.
