# 2026-09-08 — ComfyUI startup diagnostics

The isolated ComfyUI launcher now invokes Python unbuffered (`-u`) and sets
`PYTHONUNBUFFERED=1`, ensuring startup failures reach the captured logs instead
of leaving zero-byte diagnostics. Existing outputs and evidence are unchanged.
