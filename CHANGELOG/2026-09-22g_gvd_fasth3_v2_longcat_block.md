# 2026-09-22g — FastH3 V2 live profile; LongCat blocked

Used the existing Rockernow Comfy on :8188 after a restart (prior process
died in WanVideoWrapper `apply_lora` on LongCat distill LoRA).

## FastH3 V2 (`execute_fast_action`)

- Graph: official `fastvideo_fasth3_8step_v2_pruned_int8_convrot.safetensors`,
  Qwen3-VL nvfp4 CLIP on CPU, int8 video VAE, 608×352, 5 frames, 8 steps,
  `MiniMaxH3TurboSampler`. No FastH3 V1 LoRA.
- Extra **14889 MiB** (peak used 15361, baseline 472).
  14889+2048 exceeds 16 GB remaining free; production admission may
  `RESOURCE_BLOCK`.
- Prompt `514ff96e-ac61-4806-a7c9-65cafc7fcc8c`
- Promoted `fasth3_v2_unvalidated`. Digest
  `5da1be0d9bd8ab8504411492d817da1bdca26f67fc8db81e471bebf699e5df79`.

## LongCat TI2V (unmeasured)

- Distill LoRA merge: Windows access violation in WanVideoWrapper `apply_lora`.
- I2V encode: wrapper reports T2V model, rejects encoded images.
- T2V `WanVideoEmptyEmbeds`: sampler shape mismatch `4096` vs `128`.
- Failed I2V load still peaked ~14807 extra MiB. Stays disabled.

## StoryDiffusion

- Nodes load. Spec already flags >20 GB. IPAdapter remains the measured
  narrative path. Not smoked.
