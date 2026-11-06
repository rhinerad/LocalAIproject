# 2026-09-21b GVD QA loop

Implemented `docs/GVD_QA_IMPLEMENTATION_BLUEPRINT.md` in the local agent.

- New package `local_agent/gvd_qa/`: parse Comfy history for WD14 / CLIPScore / ImageReward / Qwen-VL, attach `WD14Tagger|pysssss` without replacing SaveImage, prompt-keyword ablation, evaluate gate, bounded seed reroll, generate→flush→validate VRAM phases.
- Whitelist tools: `gvd_qa_evaluate`, `gvd_qa_attach_wd14`, `gvd_qa_loop`.
- Opt-in CLI: `generate_video.py --qa-evaluate` (exit 3 on QA fail); `master_batch_runner.py --qa-loop --qa-attempts 3`.
- YRIKKA InferenceTimeScaling, wu12023 Image-Evaluation, and ComfyUI-PromptTester are not installed and are not cloned into `custom_nodes`. Caption V4 remains the owned VLM judge.
- Tests: `python local_agent/test_gvd_qa.py` (stdlib, no GPU).
