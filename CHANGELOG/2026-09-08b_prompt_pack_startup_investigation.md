# 2026-09-08b — Bounded ComfyUI startup investigation

The operator authorized direct startup reproduction and production repair. Added
`work/probe_comfy_startup.py` and diagnostic-only `startup_probe_support/sitecustomize.py`
to launch main.py directly, sample Python stacks every 45 seconds, and stop the
exact diagnostic child tree on exit. No graphs are submitted by the probe.

Pre-change baseline: `python -m unittest local_agent.test_managed_prompt_pack
local_agent.test_media_accuracy_gate -q`: 9 tests passed. Current production ledger
is error at C001_start; its only current still record is an error and videos is empty.
Prior log/output evidence is preserved. Root cause of the startup stall is still
under investigation. Code inspection separately found loss of the child handle on
startup failure, an outer 660-second timeout shorter than combined startup/render
budgets, and automatic visual approval without semantic checking.
