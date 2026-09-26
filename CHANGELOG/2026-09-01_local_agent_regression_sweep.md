# 2026-09-01 — Local-agent regression sweep and VLM ownership-test correction

## Scope

Performed a bounded, CPU-only regression sweep of the local-agent test modules
and the isolated worker-farm suite. No model was loaded, no ComfyUI backend was
started, and no render, phone bridge, queue service, or hardware-dependent
workflow was launched.

## Corrected stale test contract

`local_agent/capabilities.py::_runtime_pid_alive()` intentionally uses
PowerShell `Get-Process` on Windows rather than parsing `tasklist` output.
The old test still simulated `tasklist`'s missing-process text with a successful
exit code, making it incorrectly report an unrelated real PID as alive.

`local_agent/test_qwen25_release.py` now tests the actual contract:

- exit code `0` means the owned runtime PID is live;
- exit code `1` means it is gone;
- output text is not treated as authority.

This preserves ownership-safe lazy VLM cleanup and prevents a flaky fixed-PID
test from masking a real release failure.

## Verification

All bounded groups passed after the correction:

- 458 local-agent tests across the tracked `test_*.py` modules;
- 16 isolated worker-farm tests using
  `local_agent/worker_farm/.venv` from the repository root;
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v`:
  **124/124 valid**.

The worker-farm tests deliberately reject direct execution by path/PYTHONPATH;
the documented isolated-environment invocation was used instead.
