# 2026-09-24x — image_render: manifest records the settings the graph used

## Problem

`work/image_render.py` `manifest()` copied `model`, `steps`, `cfg`, `sampler`,
`scheduler`, `denoise` straight from argparse. `build_graph` overrides several of
them, so the receipt described a render that never happened:

- `main()` always passes `MODEL_PROFILES[profile]["model"]`; `--model` is ignored
  for every profile, yet was recorded (default `RealVisXL_V5.0_fp16.safetensors`).
- `realpro_flux` pins KSampler to `euler`/`simple`, cfg 1.0, denoise 1.0.
- every non-flux `t2i` pins the first-pass denoise to 1.0.

Evidence: `outputs/stories/history-poll-fix-verify/manifests/image_2d2834d6-6dec-437a-8460-82c9c70d6f2f.json`
top level says `RealVisXL_V5.0_fp16.safetensors`, `dpmpp_2m_sde`/`karras`, cfg
6.0, denoise 0.55; its embedded `graph` has UNETLoader
`realProV3_realProV3Unet.safetensors` and KSampler `euler`/`simple`, cfg 1.0,
denoise 1.0. That manifest is evidence and was left unchanged.

## Change

- New `effective_settings(graph)`: model from the first `CheckpointLoaderSimple`
  / `UNETLoader`; `steps`/`cfg`/`sampler`/`scheduler`/`denoise` from the
  lowest-numbered node that has a `sampler_name` input (the primary pass —
  hi-res KSampler `10` and FaceDetailer `12` always come after it; checked for
  every profile × mode × face_detail combination `build_graph` accepts).
  Graphs with no loader/sampler (`liveportrait_expression`) record `None`.
- `manifest()` top-level fields now come from `effective_settings`; the argparse
  values are kept under a new `requested` object.
- Graph construction is unchanged. No other code reads these manifest fields.

Running `effective_settings` on the evidence manifest's graph returns
`realProV3_realProV3Unet.safetensors`, steps 35, cfg 1.0, `euler`, `simple`,
denoise 1.0.

Follow-up in the same session: top-level `hires_fix` was also the raw flag,
though the pass is only built for `t2i` and never for `realpro_flux` or
`alicemix_sd15` (the evidence manifest above says `hires_fix: true` with no
hi-res nodes). `effective_settings` now reports `hires_fix` true only when a
sampler's `latent_image` links to a `LatentUpscaleBy` node, the only place that
class is emitted. The flag moves into `requested.hires_fix`. Cross-checked
against `build_graph`'s `apply_hires` rule for all 154 profile × mode ×
face_detail × hires_fix graphs it accepts: 0 mismatches.

Second follow-up, same session: top-level `width`/`height` were the flags,
which only feed `EmptyLatentImage`. The hi-res pass saves a 1.5× image (a
RealVisXL t2i at the 1024×1024 default saves 1536×1536), and every
reference-driven mode (i2i, identity/pose inpaint, face refine, hand modes,
liveportrait) takes the input image's size and ignores the flags.
- `effective_settings` predicts the saved size: `EmptyLatentImage` size ÷ 8,
  each `LatentUpscaleBy` applied with Python `round()` exactly as ComfyUI's
  `LatentUpscaleBy.upscale` does (checked in the Rockernow install's
  `nodes.py`), × 8. With no `EmptyLatentImage`, `None`.
- New `png_size(path)` reads IHDR. `main()` adds `width`/`height` to each
  `verified_outputs` entry, then `apply_measured_size` sets the top-level
  fields to the measured size when all outputs agree. Measured wins over
  predicted.
- The flag values move into `requested.width`/`requested.height`.

Checked read-only against existing receipts (`outputs/stories/*/manifests/image_*.json`,
680 files; 395 with a graph and an on-disk PNG): predicted size equals the
real PNG's IHDR size in 177/177 t2i receipts (161 RealVisXL with hi-res,
10 without, 6 realpro_flux). The other 218 are reference-sized and predict
`None`; completion measurement covers them. No receipt was modified.

## Tests

`local_agent/test_production_integrity.py` `ImageManifestEffectiveSettingsTests`:
realpro_flux values match graph nodes `1`/`7` with `requested` preserved;
profile model beats `--model` and t2i records the first pass (denoise 1.0), not
hi-res node `10`; empty graph records `None`; `hires_fix` is true only for a
RealVisXL t2i graph with the pass, and false for `--no-hires-fix`, AliceMix
t2i, and i2i, with `requested.hires_fix` keeping the flag; width/height are
1536² with hi-res, 832×1216 without, 1504×1168 for 1000×776 (half-latent
rounding), `None` for i2i; `png_size` reads a real PNG and rejects non-PNG;
`apply_measured_size` replaces the prediction only when all outputs agree.

The `main()` completion path itself was not executed (it requires a render).

- `python -m unittest test_production_integrity` (from `local_agent/`): 57 OK
- `python -m unittest test_render_story_image test_image_render_cleanup test_story_image_plan`: 41 OK
- `python -m unittest test_image_render` (from `work/`): 17 OK

No render was started; no GPU work.
