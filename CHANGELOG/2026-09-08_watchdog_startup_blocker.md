# 2026-09-08 — Repeated isolated ComfyUI startup blocker

The watchdog observed two consecutive isolated ComfyUI starts that never
exposed port 8188 or advanced beyond initialization, despite the 600-second
bounded readiness window. The owned production worker trees were terminated;
no unrelated Comfy Desktop process or prior evidence was touched. Production
remains paused at corrected still C001 pending a safe diagnosis of the host
ComfyUI startup conflict.
