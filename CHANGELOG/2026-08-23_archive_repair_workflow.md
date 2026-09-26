# Archive restoration and AI-video upscale workflow — 2026-08-23

- Added `workflows/ARCHIVE_REPAIR_AND_AI_VIDEO_UPSCALE.json`.
- The single ComfyUI graph has a restoration path: Video Helper Suite load,
  Florence candidate mask, 4px GrowMask, ProPainter temporal repair, SUPIR, and
  a single final Video Helper Suite encode with source audio.
- Its second mode is direct AI-video enhancement: bypass `ProPainterInpaint` so
  source tensors flow straight into SUPIR with no intermediate compression.
- The active ComfyUI installation lacked ProPainter and SUPIR nodes; their
  upstream custom-node repositories were added to the active Rockernow instance.
- Existing dependencies already cover OpenCV, Transformers, OpenCLIP, Pillow,
  OmegaConf, and Accelerate. `pytorch-lightning` remains pending because this
  machine's TLS credential provider rejected both pip and curl before any
  package was downloaded (`SEC_E_NO_CREDENTIALS`); the stalled installer was
  stopped cleanly. No package state was partially changed.
- No render was started and no existing workflow, render artifact, or pipeline
  state was changed.
