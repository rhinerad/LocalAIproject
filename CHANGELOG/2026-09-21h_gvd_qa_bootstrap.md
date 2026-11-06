# 2026-09-21h GVD QA bootstrap and local backend

Workstation pass: ComfyUI :8188 and Caption V4 :11436 were down; RTX 5080 idle (~301 MiB used, ~15677 MiB free); Ollama :11434 up with empty `/api/ps`. No custom nodes were installed.

- `local_agent/gvd_qa/bootstrap.py` records GPU/Comfy/Ollama/Caption V4, family scan, fail-closed activation report, stages `ComfyUI-GVD-QA` to `local_agent/runtime/gvd_qa/quarantine`, writes WD14 CPU ORT settings.
- `LocalQaClient` produces GVD report history without YRIKKA nodes. CLIP/checklist/ImageReward are injected or fail closed (`adapter_required`).
- Local fixtures `fast_qa_local.api.json` / `qwen_qa_local.api.json` / `reward_qa_local.api.json`.
- Unmeasured policy `profiles/local_unmeasured.json` (explicitly not 5080 calibration).
- Tests: `python local_agent/test_gvd_qa_local.py`.
