# 2026-09-01 — Execution-first retry and Windows status-marker lock tolerance

## Operator outcome

For a direct desktop request to carry out safe work, the local agent now makes
one bounded corrective model turn when the first reply only gives the operator
instructions and no tool has been attempted. The correction directs the model
to select and use the appropriate available tool, then report the result or a
specific missing condition. This prevents an ordinary request such as “continue
with the validation steps” from becoming a terminal command the agent itself
could have performed.

The retry is intentionally limited to one turn. It does not authorize renders,
downloads, protected-file changes, binary patches, GPU workloads, or remote
phone capabilities beyond their existing gates.

## Reliability correction

On Windows, a transient lock on `runtime/chat_busy.json` during cleanup no
longer makes an otherwise completed chat reply fail. `router.set_chat_busy()`
retries the marker removal briefly and leaves the aging marker in place if it
is still locked.

## Verification

- `python local_agent\\test_native_tool_calling.py` — 51 tests passed.
- `python local_agent\\test_agentic_state.py` — 12 tests passed.
- `python local_agent\\test_router_switching.py` — 42 tests passed.

No GPU workload, render, ComfyUI process, download, model load, or PowerInfer
operation was started for these changes.

## Follow-up: exact JSONL repair continuity

The old calibration-tool description contained a placeholder path. A small
model could copy that literal `...` text after a real validation failure rather
than reuse the returned file path. The description now explicitly rejects
placeholders, examples, and guessed paths.

`repair_jsonl_format` is a bounded desktop text-edit tool for one observed
failure mode: a top-level JSON array accidentally saved with a `.jsonl`
extension. It losslessly writes one existing object per line to the same path,
then the local agent immediately revalidates that exact path. It never creates
records, changes values, approves a file, or unlocks model/predictor/GPU/render
work. Arbitrary malformed fragments are refused rather than guessed.

The per-chat task checkpoint now retains up to four exact active file paths from
tool arguments/results, so a compacted transcript cannot erase a verified path.
The deterministic repair route is used only after a failed calibration intake
and an explicit desktop repair request.

The desktop server now replays up to four bounded tool receipts from the same
saved conversation as factual context for the next turn. It does not replay raw
tool protocol messages or read another chat. This lets a restart recover the
same failed validator path even when the original turn predates task-path
checkpointing.

Additional verification:

- native tool suite: 54 tests passed, including exact-path repair/revalidation
  from both live and saved-chat evidence;
- task-checkpoint suite: 13 tests passed, including active-path retention;
- router suite: 42 tests passed.
