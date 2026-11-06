# 2026-09-21e GVD QA blueprint

Incorporated `docs/GVD_QA_IMPLEMENTATION_BLUEPRINT.md` from
`A:\Users\rhine\AppData\Local\Temp\codex-file-preview-Qys1Fv\GVD_QA_IMPLEMENTATION_BLUEPRINT.md`.

- Root module `gvd_qa.py`: candidate persist, `Policy`, `evaluate_fast` / `evaluate_qwen`, WD14 advisory traits, `generate_until_accepted`, `accepted_i2v_image`, idle-queue `/free`.
- Review-only adapters `local_agent/gvd_qa/comfy_adapters.py` (`GVDMetricReport`, `GVDQwenChecklist`, `GVDRewardReport`, `GVDScoreCLIP`, `GVDPromptPlan`). Not installed into Rockernow `custom_nodes`.
- API graph fixtures under `local_agent/gvd_qa/fixtures/`.
- `LeasePhaseController` wraps the existing GPU lease; `enter()` is never a no-op.
- `generate_video.py --require-qa-receipt --qa-receipt accepted.json` binds only the hash-locked still to I2V.
- Tool `gvd_qa_accepted_still`.
- Tests: `python local_agent/test_gvd_qa_blueprint.py` (seven mocked cases from the blueprint). No GPU models loaded.
