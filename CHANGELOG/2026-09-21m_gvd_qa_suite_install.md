# 2026-09-21m GVD QA suite install

- User authorized install of remaining blueprint nodes and weights.
- Pinned clones into Rockernow `custom_nodes`: YRIKKA InferenceTimeScaling `e368962c`, wu12023 Image-Evaluation `6976a642`, drphero PromptTester `c1c9d314`, plus `ComfyUI-GVD-QA` with trust receipt. YRIKKA Qwen/ImageReward imports are lazy so Comfy starts without outlines or a working ImageReward forward pass.
- Did not `pip install -e` YRIKKA (would pin `transformers==4.49.0` over Rockernow 5.10.2). Did not download Qwen2.5-VL Instruct 3B/7B; Caption V4 on `:11436` remains the checklist.
- Agent CPU scorers: `gvd_qa/scorers.py` CLIP (`max(100*cosine,0)`, unit `torchmetrics_clipscore_0_100`), DINO vits16, ImageReward. WD14 CPU already pinned.
- Live `/object_info` after idle restart: `activable=true`, adapters installed, fast/qwen/reward/prompt graphs ok.
- CPU smoke on `br24_C017_start_00001_.png`: CLIP 26.16, DINO self 1.00, ImageReward -2.26, WD14 tags unchanged; VRAM stayed 355 MiB. These are unmeasured 5080 numbers, not production floors.
- ImageReward 1.5 needed local transformers-5 shims in both agent and Comfy site-packages (`BLIP/blip.py` enc token id, `BLIP/med.py` tied weights and invert_attention_mask). Reapply with `gvd_qa/patch_imagereward_tf5.py` if pip overwrites them.
