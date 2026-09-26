# 2026-09-21n Persisted still QA

- `evaluate_persisted_candidate` scores one saved PNG: no generation, no seed reroll. Writes `accepted.json` or `blocked.json`.
- `run_persisted_still_qa` + `cpu_local_client` bind CPU CLIP/ImageReward/WD14 and an injected checklist (Caption V4 on live).
- Policy `observed_5080_finite_clip.json`: CLIP floor 0 (finite-only), no ImageReward floor. Rubric `br24_c017_rubric.json` (yellow_walls, person_visible). Not production calibration.
- Evidence insert now stores `qwen_checks`. Tests: `python local_agent/test_gvd_qa_persisted.py`.
- Live `br24_C017_start_00001_.png`: CLIP 26.16 admitted; WD14 camera/person tag_supported; Caption V4 yellow_walls=fail, person_visible=pass; ImageReward skipped; `blocked.json`; VLM peak 10886 MiB then 357 MiB. I2V stays blocked. Report: `local_agent/runtime/gvd_qa/smoke_persisted_still.json`.
