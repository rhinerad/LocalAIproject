# 2026-09-08 — Production watchdog resume and cold-start fix

The corrected prompt-pack run was resumed from the durable ledger after the
stale Equal Shares owner was confirmed inactive. A second failure was diagnosed:
the isolated ComfyUI backend exceeded the old 180-second readiness timeout while
importing its runtime. The bounded timeout is now 600 seconds, and the worker was
restarted with an empty still-result ledger so corrected prompts are rendered
again without deleting prior evidence. Current supervisor PID is recorded in
`local_agent/runtime/managed_tasks/f8f7f70e364d40c0/production_progress.json`.
