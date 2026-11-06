# 2026-09-21l — live TiledDiffusion upscale_still profile

Used the existing Rockernow Comfy on :8188. Did not start a second backend.

## Upscale (`upscale_still`)

- Graph: RealVisXL + `TiledDiffusion` Mixture of Diffusers, 512 tiles,
  1.5× `gvd_identity_ref.png`, 4-step euler denoise 0.35.
- First POST failed: `VAEDecodeTiled_TiledDiffusion` raised
  `'Decoder' object has no attribute 'give_pre_end'` on the SDXL VAE.
  Retry used core `VAEDecodeTiled`.
- Prompt `856e0175-63ad-4a29-a573-03cfe8f8bdad`
- Baseline 423 MiB; peak used 7559 MiB; extra **7136 MiB**. Fits 2048 MiB headroom.
- Promoted `tiled_diffusion_unvalidated`. Registry digest
  `5da25ea2d602bb8487a2dc5b8f9270fe538184ea8812627bc3d818cccc9e75b4`.
