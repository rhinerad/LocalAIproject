# 2026-09-08 — Semantic QA caught camera leakage

The exact Qwen2.5-VL Caption V4 review is now operational and rejected the fresh
C001 still for visibly showing the camera body and lens. This confirms the gate
is catching the failure mode that mechanical checks cannot. Still-job prompts now
carry an absolute off-screen-camera framing rule; the failed evidence remains
preserved and will be regenerated under a new prompt hash.
