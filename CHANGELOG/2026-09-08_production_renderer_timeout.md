# 2026-09-08 — Renderer timeout and diagnostics

Bounded the production supervisor's image-render subprocess to 660 seconds,
matching the renderer's 600-second ComfyUI readiness limit with diagnostic
margin. A hung isolated backend now becomes a recorded failure instead of an
unbounded wait. Existing outputs and evidence are preserved.
