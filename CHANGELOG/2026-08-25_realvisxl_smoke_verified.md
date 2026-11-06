# 2026-08-25 — RealVisXL storyboard renderer smoke verified

## Verified result

- Exact checkpoint: `RealVisXL_V5.0_fp16.safetensors`.
- One deliberately approved, isolated 1024×1024 text-to-image smoke render completed.
- Parameters: seed `20260825`, 28 steps, CFG 6, `dpmpp_2m_sde`, `karras`.
- Output: `outputs/stories/_comfy_output/stories/realvisxl-smoke/renders/20260824_235652_00001_.png`.
- Reproducibility manifest: `outputs/stories/realvisxl-smoke/manifests/image_386fdb12-5ace-4b56-a97b-2e2d81625600.json`.
- Visual audit: photoreal portrait output, no obvious anatomy, text, watermark, or framing defect for this smoke prompt.

## Guard verification

- The image renderer used an isolated, core-only ComfyUI backend on `127.0.0.1`.
- Equal Shares was not started, its outputs were untouched, and its queue owner was never reused.
- The renderer released `work/runtime/image_render_owner.json` after completion; GPU returned to idle.
- A Windows console encoding failure during the first actual sampler completion was fixed by launching the owned backend with UTF-8 (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`). The renderer now also fails promptly if its own backend exits while output collection is pending.

## Verification

- `python work/test_image_render.py` — 6/6 passed after the UTF-8/fail-fast change.
