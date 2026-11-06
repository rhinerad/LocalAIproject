# 2026-08-29 - GPU busy false positive: idle Steam client

## Problem

On Windows WDDM, `nvidia-smi --query-compute-apps` reported the idle Steam
launcher (`steam.exe`) alongside ordinary desktop GPU contexts. The local-agent
router classified every non-browser process as a foreign compute owner, so this
small display allocation forced chats onto the CPU even when ComfyUI was closed,
port 8188 was not listening, no render owner was live, and GPU utilization was
zero.

## Change

- Added the Steam launcher executable to the router's explicit low-VRAM desktop
  display-context allowlist.
- Preserved every real GPU reservation boundary: live render queue ownership,
  ComfyUI on port 8188, unknown process owners, active game executables, and
  material foreign VRAM use above the 2500 MB threshold.
- Added a router regression case for an idle `steam.exe` context at 121 MB.

## Verification

`python -m unittest local_agent.test_router_switching -v` passes after this
change. The test suite does not load a model, start ComfyUI, or start a render.
