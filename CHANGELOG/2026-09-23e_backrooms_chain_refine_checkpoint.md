# 2026-09-23e — Backrooms chaining: refine checkpoint at the chain ceiling

Follows 2026-09-23d, which wired the clip-to-clip chaining from
`backrooms-frame-chaining-spec.md` but left out step 5. In 23d, a clip past
`CHAIN_MAX_CONSECUTIVE` got a **fresh FLUX still**. That is a hard visual cut
in the middle of a continuous scene, and the spec rules it out.

Now a `context_video` clip past the ceiling gets a **refine checkpoint**. The
previous clip's actual last frame goes through a low-denoise FLUX img2img
pass, and MiniMax animates the result. The chain counts from 0 again after it.

Real cuts are unchanged and still get a fresh still:

- the reasoner answers `reference_image` or `none`
- the camera mode changes
- a character re-enters

`--continuity` still defaults to `off`. No render was run.

## Code

- `local_agent/dspy_orchestrator.py`
  - New `bind_refine_checkpoint()`. It rewires the existing FLUX branch:
    `LoadImage 1003` → `ImageScale 1004` (to node 5's size, 1280×704,
    lanczos, center crop) → `VAEEncode 1005` (FLUX VAE `10`) → `KSampler 3`
    `latent_image`, with `denoise` set to the refine value.
  - `EmptyFlux2LatentImage 5` is removed.
  - Node 3 keeps its model (`41`), positive (`12`←`6` start_prompt) and
    negative (`7`). The refine is therefore steered by the same model and
    text a fresh still would use. This path has no LoRA nodes to carry over.
  - `20.first_frame` stays `["8",0]`: MiniMax gets the refined image.
  - Optional core `ImageSharpen 1006` (alpha > 0 only). Every consumer of
    `["8",0]` is rewired to it.
  - Raises if nodes 3, 5, 8 or 10 are not the expected classes, or if denoise
    is not strictly between 0 and 1. The alternative, silently falling back
    to a plain T2I still, is worse.
  - `build_minimax_graph` / `generate_minimax_clip` take `refine_frame_path`,
    `refine_denoise` and `refine_sharpen_alpha`.
    - A refine frame cannot be combined with `start_frame_path`, because that
      path bypasses FLUX: this raises `ValueError`.
    - Refine params are part of the output-prefix hash.
  - `trim_graph_to_stills_only` saves from `1006` when it exists. Stills-only
    plus refine yields just the refined PNG.
  - New helper `_comfy_input_name()`, factored out of `bind_h3_image_frames`
    with no behavior change.
- `generate_video.submit_comfy`: passes the three refine kwargs through.
- `batch_run_backrooms_gvd.py`
  - `continuity_policy(..., reset="refine")`: at the ceiling it returns
    `("refine_checkpoint", "chain_ceiling_refine")`. With
    `reset="fresh_still"` it returns the old `("fresh_still", "chain_ceiling")`.
    Scene-change guards are checked first, so a real cut past the ceiling is
    still a fresh still.
  - New CLI flags:
    - `--chain-reset refine|fresh_still` (default `refine`)
    - `--refine-denoise` (default `REFINE_DENOISE = 0.30`, **untuned**)
    - `--refine-sharpen` (default `0` = no node)
    - Invalid values fail at argparse, before anything runs.
  - Live refine uses the same preconditions and fallbacks as a chain. Any of
    these gives a fresh still: previous clip not SELECTED, ref2vid clip, or an
    extract/upload error.
  - The frame is uploaded as `refine_<cid>_<frame>.png` and submitted as
    `refine_frame_path`.
  - `progress.json` entries for these clips have:
    - `mode_used: refine_checkpoint`, `chain_depth: 0`
    - `refine_frame_path`, `refine_denoise`, `refine_sharpen_alpha`
    - `source_clip_id`, `source_video_path`, `chain_frame_path`
    - `start_frame_source: refined_from:<prev>`
  - Shadow records gain `shadow_would_refine`.
  - The inline pipeline-rules block in `main()` moved unchanged into
    `apply_pipeline_rules()` so the tuning script uses the batch's exact prompts.
- `scripts/refine_denoise_compare.py` (new). It runs the FLUX refine only
  (stills-only) on one real chained frame at each `--denoise` (default 0.2
  and 0.35), and writes a report under
  `local_agent/runtime/gvd_backrooms_batch/refine_tuning/`.
  - It refuses to run unless ComfyUI is already listening. It never starts a
    backend.

## Upscale nodes (spec step 5: confirm, don't assume)

Checked on disk; the server was down, so this was not confirmed through
`/object_info`.

- `Rockernow\ComfyUI\custom_nodes` has `comfyui_ultimatesdupscale`,
  `ComfyUI-Upscaler-Tensorrt` and `ComfyUI-SeedVR2_VideoUpscaler`. Core
  `ImageSharpen` and `ImageUpscaleWithModel` are present.
- Upscale model files (`4x-UltraSharp`, `RealESRGAN_x2plus`,
  `2xLexicaRRDBNet_Sharp`, …) are only in `ComfyUI-Shared\models\upscale_models`.
  Rockernow's own `models\upscale_models` is empty. I could not find the path
  mapping offline.
- Decision: no upscale node. The still and the I2V input are both 1280×704, so
  there is no resolution gap. Sharpening, if needed, uses core `ImageSharpen`,
  which needs no model file.

## Evidence

- Offline `build_minimax_graph(clip_id=br_c013, refine_frame_path=…, refine_denoise=0.3)`
  on the real template:
  - node 5 is absent
  - `3.latent_image=["1005",0]`, `3.denoise=0.3`
  - `1005 = VAEEncode(pixels=1004, vae=10)`
  - `20.first_frame=["8",0]`
  - no dangling links
  - stills-only keeps 1003–1006 and saves from `1006`
- `VAEEncode` through `flux2-vae` should produce the same 128-channel /16
  latent that `EmptyFlux2LatentImage` builds (checked in Rockernow
  `comfy_extras/nodes_flux.py`). **Not verified by a render.**
- Replay of the 23d shadow v3 reasoner decisions (`dry_run_report.json`)
  through the new policy, with no LLM call:
  - with `reset=fresh_still` it reproduces v3 exactly
  - with `reset=refine`, 76 chain / 14 refine / 12 fresh. The fresh stills
    are 1 first clip, 3 camera-mode changes (C015, C016, C063) and 8
    character re-entries.
  - Refine clips: C006 C011 C021 C026 C031 C036 C041 C046 C068 C079 C084
    C089 C094 C099.
  - Result: 12 T2I stills instead of 102.
- Tests:
  - `test_batch_run_backrooms_continuity.py` has 49 tests. 12 are new or
    rewritten: the refine policy, both reset modes, refine live record and
    fallbacks, main-loop submit kwargs and `progress.json`, and arg
    rejection, plus 4 graph tests against the real template.
  - `test_batch_run_backrooms_gvd.py` 6 and `work/test_scene_reasoner.py` 20
    also pass.
- `verify_p0_offline.py` still fails on the pre-existing missing
  `handoff/gvd_core.py`, the same as in 23d.
- Backups: `*.bak_refine_20260923T210521` for the four edited files.

## Not done — required before `--continuity live` on a long run

1. **Denoise tuning.** Run
   `scripts/refine_denoise_compare.py --clip C013 --source-video <C012 mp4>`,
   then compare 0.2 and 0.35 with the unrefined frame. Check whether it is
   the same character, pose and scene with less codec softness. Update
   `REFINE_DENOISE` and record the result here.
2. **Small live test** from 23d, extended to cover a refine. For example
   `--clip C012 … --clip C016 --continuity live --chain-max-consecutive 2`:
   - expected: C012 fresh, C013 and C014 chained, then C015 fresh for the
     camera change (C015 is the fall).
   - To test a refine without a camera change, use four same-mode clips with
     `--chain-max-consecutive 1`.
   - Verify with `ffprobe -show_entries format_tags=prompt`. The refine clip's
     embedded workflow must show `LoadImage 1003`→`VAEEncode 1005`→`KSampler 3`
     at the refine denoise, and no `EmptyFlux2LatentImage`.
3. The 23d shadow review showed the reasoner never answers `reference_image`.
   The deterministic guards remain the only real scene-boundary protection.
