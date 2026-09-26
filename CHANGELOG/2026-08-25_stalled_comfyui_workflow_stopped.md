# 2026-08-25 — Stalled ComfyUI workflow stopped at operator request

## Situation

- The ComfyUI backend on port 8188 had retained a single workflow since
  2026-08-25 04:47 UTC while GPU utilization remained at 0% for hours and
  approximately 11.8 GB of VRAM remained allocated.
- A normal `POST /interrupt` was accepted by ComfyUI but did not release the
  queued workflow or GPU allocation after a controlled wait.

## Action

- After the operator explicitly requested that the stalled workflow be killed,
  only the confirmed Python process listening on port 8188 was stopped.
- No project evidence, raw media, manifests, prompts, or render outputs were
  deleted, moved, renamed, or overwritten.

## Result

- Port 8188 is no longer listening and the GPU allocation fell to its idle
  baseline. The Equal Shares pipeline remains paused; this did not authorize a
  restart, queue resume, or any new render.
