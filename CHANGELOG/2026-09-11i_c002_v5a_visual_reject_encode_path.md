# 2026-09-11i — C002 v5a visual reject + encode-path root cause

## Attempt
- id: `372f98ca4b764521be5678ba8aed6b13`
- still SHA-256: `2b8136b57e710d1cac798757afc985532be99c7bd523421fc01f3570586b334f`
- policy: `c002-raised-hand-erase-v5a` / `bgnoise-prefill-sd-erase-v1`
- decision: **operator reject** (Local Agent Debugger)

## Visual
- Flat light-blue polygonal slab over raised-arm corridor (not sofa/wall).
- VLM semantic pass overruled (claimed background-consistent fill + hands at side).

## Encode-path finding
- Graph used `VAEEncodeForInpaint` (grow_mask_by=0) then `ImageCompositeMasked`.
- `VAEEncodeForInpaint` zeros/masks latent pixels inside the hole, so the bgnoise **prefill on the reference PNG does not survive into the latent**.
- That matches the whole teal/green/blue blob family (v1–v5a): fill from empty latent, not from surrounding pixels.
- Prefer next: `VAEEncode` + `SetLatentNoiseMask` (already used in hand_crop path) so prefilled pixels participate, then composite.

## Not doing
- Do **not** run v5b on this plate (would paint onto the blue slab).
