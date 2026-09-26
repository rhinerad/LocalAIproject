# 2026-09-08 — Reviewed prompt-pack media accuracy gate

Synced with Grok r98 production state (source SHA `72a7c2e5...`, 204 stills,
102 videos). Added `local_agent/media_accuracy_gate.py`, a deterministic gate
that validates generated still files and enforces the reviewed pack's apartment/
Backrooms, camcorder, and no-motion controls. The production worker now records
the gate result and stops before video generation on failure. Added two regression
tests. Semantic VLM review remains explicitly `not_run` unless the exact approved
Qwen2.5-VL runtime is intentionally invoked while the GPU is idle.

The already-running r98 worker was not interrupted; it loaded the pre-gate code.
The gate applies on its next resume/restart. No model, checkpoint, prompt source,
or evidence was overwritten, and no unrelated process was stopped.
