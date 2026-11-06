# 2026-09-11j - C002 v5a2 latent-noise-mask erase path

## Why
- v5a (`VAEEncodeForInpaint`) zeroed the bgnoise prefill in latent space, producing a flat light-blue polygonal slab.
- Next still-only retry must keep prefilled sofa/wall pixels via `VAEEncode` + `SetLatentNoiseMask`.

## Code
- `work/image_render.py`: `build_graph(..., use_latent_noise_mask=False)`; identity-inpaint branch can emit VAEEncode+SetLatentNoiseMask node 23; CLI `--use-latent-noise-mask`.
- `work/run_prompt_pack_production.py`: pass flag from identity_control; recovery order `v5a2_failed → v5b (hang-corridor-on-v5a2-plate-v1)` then `v5a_failed → v5a2 (bgnoise-prefill-latentmask-v1, denoise 0.52)`; keep `v4b → v5a`.

## Tests
- Expect `v5a → v5a2` (not v5b); add `v5a2 → v5b`.
- Graph assertion: `use_latent_noise_mask=True` yields VAEEncode + SetLatentNoiseMask.

## Live
- One C002_start v5a2 attempt; force-stop supervisor before C002_last.

## Live result (2026-09-11)
- attempt: `1fd665a494dd49378bfb6420e85f0d0b`
- policy: `c002-raised-hand-erase-v5a2` / `bgnoise-prefill-latentmask-v1`
- still SHA-256: `956bace505fb141da81e3e0c2c7c18c02ce63605aa2075376d2eee07ecbb70ae`
- graph encode: `4=VAEEncode`, `23=SetLatentNoiseMask`, KSampler latent_image=`[23,0]` (not VAEEncodeForInpaint)
- QA copy: `work/_debug_c002_inspect/v5a2_1fd665a494dd49378bfb6420e85f0d0b_still.png`
- production: force-stopped after v5a2 still; status `paused_for_operator_review`; C002_last not continued
- tests: `python -m unittest work.test_still_retry_not_stop work.test_image_render` → 55 OK
