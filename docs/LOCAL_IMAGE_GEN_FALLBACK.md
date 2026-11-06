# Local image generation — fallback for boundary frames

A local alternative to `docs/GEMINI_REFERENCE_IMAGE_GUIDE.md` for producing a first or last frame when one is genuinely needed.

The model inventory at the end of this document was verified against `A:\Users\rhine\ComfyUI-Shared\models\` on August 10, 2026. The workflows themselves have **not** been built or tested — treat the recommended approach as a plan, not a working pipeline.

---

## When this applies

Only after the salvage ladder is exhausted. In order: vary prompt and seed at 20 steps; simplify or slow the motion; split the action into ordered beats; shorten the clip; clean cut or hold on an approved frame; build an insert or subtle motion from existing approved frames. Working examples of the last rung live in `work/salvage_*.py`, `work/select_*.py`, and `work/repair_*.py`.

A new boundary image is the last resort, because every new image is a new opportunity for identity to drift. An approved frame that already exists is always safer than a generated one that doesn't.

## Local versus Gemini

Gemini's advantage is that it follows multi-image identity references and long prose constraints unusually well, which is why `docs/GEMINI_REFERENCE_IMAGE_GUIDE.md` exists and is the primary path.

Local generation is worth reaching for when: the render is between clips and the GPU is free; the needed frame is a *variation* on an existing approved frame rather than a new composition, which makes it an inpainting or img2img job rather than a text-to-image job; or you want the frame to inherit the exact grain, palette, and lens character of the surrounding footage, which a local pass conditioned on a real neighbouring frame does better than any external service.

That last case is the strongest argument for local. A Gemini frame is a photograph of the scene; a local img2img pass over an adjacent approved frame *is* the scene.

## The GPU constraint comes first

**Do not run local image generation while the render supervisor is working.** One ComfyUI backend at a time, on port 8188. Check for a running `render_until_complete.py`, check whether 8188 is bound, and check that `outputs/equal_shares/runtime/render_supervisor.log` has stopped advancing.

If the supervisor is alive, either wait for a clip boundary and ask the human to pause it, or use Gemini instead. Starting a second backend to make one image is not worth corrupting a 124-clip run.

## Step 1 — pick the approach that matches the need

**Tier A — instruction editing over an approved neighbour. This is the recommended path.** `Qwen-Image-Edit-2509-Q5_0.gguf` is installed in `models\unet\`. It takes an existing image plus a plain-language instruction — "move his right hand to the closed wallet," "turn the seated man's head toward the window" — and edits only what the instruction names. Identity, wardrobe, architecture, lighting, and film grain are inherited from the source frame rather than regenerated, which sidesteps the drift problem entirely.

Feed it the nearest approved boundary frame from `outputs/equal_shares/frames/scene_###/`. This is the single best tool available locally for this project, because almost every boundary frame the film needs is a small variation on a frame that already exists and is already approved.

**Tier B — img2img at low denoise.** Where the whole frame must shift slightly and no clean instruction describes it, run the nearest approved frame through img2img with `flux1-dev-fp8.safetensors` or an SDXL realism checkpoint at a denoise low enough to preserve identity — start around 0.35 to 0.45 and go lower if faces move. Above roughly 0.6 you are generating a new person and should expect to fail the acceptance gate.

Add a ControlNet over the neighbouring frame whenever geography must hold. `controlnet-union-sdxl-1.0-promax.safetensors` covers depth, softedge, and pose in one model, and `mistoLine_rank256.safetensors` is available for line conditioning. Both are SDXL-family, so pair them with an SDXL checkpoint, not with Flux. Screen direction and room layout are among the things the acceptance gate checks hardest.

**Tier C — text-to-image for a genuinely new composition.** Weakest option, because the installed stack has **no IP-Adapter and no PhotoMaker** — the `photomaker`, `style_models`, `inpaint`, and `facerestore_models` folders are all empty, and no `ipadapter` folder exists. There is no direct way to condition a fresh generation on `alex_vale_master_v1.png`.

There is an indirect route: `insightface\inswapper_128.onnx` with the `buffalo_1` pack is installed, which means a ReActor-style face swap is possible. Generate the composition with Flux or SDXL, then swap Kent's face in from the master reference. Treat this as a last resort — `inswapper_128` operates at 128 pixels, so at a 736 × 416 target it will hold identity in close shots and add little in wides, and it can leave a visible seam under the mustache. If Tier C is where you have ended up, Gemini is very likely the better answer.

**Not available locally:** dedicated inpainting checkpoints, IP-Adapter, PhotoMaker, style models, face restoration. Do not write a workflow that assumes any of them.

## Step 3 — match the target format

The frame must be usable as an H3 anchor, which means it must match generation geometry:

- **736 × 416**, 16:9, a multiple of 32 in both axes.
- 8-bit, sRGB, PNG.
- No alpha channel.

Generating larger and downsampling to 736 × 416 is acceptable and often better, since more pixels during generation means a better-resolved face before the downsample. Do not deliver a frame at a different aspect ratio and expect the runner to letterbox it sensibly.

Write to `outputs/equal_shares/frames/scene_###/` alongside the existing boundary frames, following their naming convention, and **always as a new version**. Never overwrite an approved reference.

## Step 4 — the acceptance gate is the same one

A locally generated frame earns no leniency for being local. Reject it if any character fails to match the correct reference sheet; if the number or position of people is wrong; if hands or anatomy are malformed; if architecture, props, wardrobe, or screen direction drift from the neighbouring approved frame; or if it contradicts the clip's entry in `story_config.json`. Looking good is not the standard.

Check the opening locks specifically if the frame belongs to scene 000: one woman, the receptionist, always behind the staff window; exactly two male visitors, both on the public side, entering through the separate doorway; one chair at screen-left; no glass gate, fence, invented divider, extra chair, or third man; a Narrator who does not resemble Kent.

## Step 5 — wire it in and render only the affected clip

Update the clip's `first_frame` or `last_frame` path in `outputs/equal_shares/story_config.json`. Change nothing else. Then:

```powershell
$Python = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"
& $Python ".\outputs\minimax_story_runner.py" ".\outputs\equal_shares\story_config.json" --check
& $Python ".\outputs\minimax_story_runner.py" ".\outputs\equal_shares\story_config.json" --resume --only <clip-id>
```

Never regenerate unrelated approved clips to "keep things consistent." They are already accepted and their raws are already preserved.

## Step 6 — record it

In `archive/superseded_docs/HANDOFF.md` and the project notes, record why a new image was necessary and which salvage rungs failed first, which references were used, the exact prompt and settings, the model files involved, the output path and version, and the acceptance decision with reasons. A generated boundary frame that nobody can trace back to a justification will be re-litigated by the next person to look at the film.

---

## Inventory

Verified against `A:\Users\rhine\ComfyUI-Shared\models\` on 2026-08-10. Only entries relevant to boundary-frame work are listed; the tree holds a great deal else.

**Image editing — the recommended path**

- `unet\Qwen-Image-Edit-2509-Q5_0.gguf` — instruction-based image editing

**Text-to-image and img2img**

- `checkpoints\flux1-dev-fp8.safetensors`
- `unet\flux2_dev_fp8mixed.safetensors`, `diffusion_models\flux-2-klein-9b.safetensors`
- `checkpoints\sd_xl_base_1.0_0.9vae.safetensors`
- `checkpoints\dreamshaperXL_lightningDPMSDE.safetensors`
- `checkpoints\realisticVisionV60B1_v51HyperVAE.safetensors`
- `checkpoints\epicrealism_naturalSinRC1VAE.safetensors`
- `checkpoints\v1-5-pruned-emaonly-fp16.safetensors`

**Geometry conditioning (SDXL family)**

- `controlnet\controlnet-union-sdxl-1.0-promax.safetensors` — depth, softedge, pose
- `controlnet\controlnet-canny-sdxl-1.0-fp16.safetensors`
- `controlnet\mistoLine_rank256.safetensors`

**Identity (indirect only)**

- `insightface\inswapper_128.onnx` and `insightface\buffalo_1` — ReActor-style face swap, 128 px
- `clip_vision\clip_vision_h.safetensors`, `clip_vision\sigclip_vision_patch14_384.safetensors` — present, but with no IP-Adapter to consume them

**Upscaling** — `RealESRGAN_x2plus.pth`, `RealESRGAN_x4plus.pth`, `4x-UltraSharp.pth`, `4x_NMKD-Siax_200k.pth` and others. Remember that upscaling cannot repair anatomy or identity drift.

**Confirmed absent** — `models\inpaint\`, `models\photomaker\`, `models\style_models\`, `models\facerestore_models\` are all empty. There is no `ipadapter` folder.

**Confirmed present, for reference** — `diffusion_models\minimax_h3_fl2va_pruned_int8_convrot.safetensors`, the production video model.

**Still unknown** — VRAM headroom with the H3 stack unloaded. Measure before committing to Flux or Qwen-Image-Edit at size.
