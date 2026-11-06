# 2026-09-21g GVD QA remaining blueprint items

Finished the leftover items from `docs/GVD_QA_IMPLEMENTATION_BLUEPRINT.md` in code. Live GPU installs of YRIKKA / wu12023 / PromptTester remain fail-closed until `/object_info` and a trust receipt exist.

- `gvd_qa.py`: job resume + journal reconcile, best-of-K among qualifiers, `ablation_jobs`, CLIP token audit, generation save redirect (drops ungated I2V), graph class checks, subject-crop node, ONNX CPU-only assertion, `policy_from_mapping`.
- Evidence SQLite (`qa_evidence`, `qa_experiments`) insert-only; also added to `gvd_tool_router` schema.
- `pipeline.run_still_qa` binds fixtures and refuses missing node classes.
- `LeasePhaseController`: per-phase worker URLs, 2GiB headroom `RESOURCE_BLOCKED`, GPU lease as a real context manager.
- WD14 CPU worker settings writer; `ComfyUI-GVD-QA` staged package; `stage_comfy_gvd_qa` copies to live `custom_nodes` only with `install=True` and `trust_receipt`.
- `generate_video.py` I2V requires an acceptance receipt unless `--allow-ungated-i2v`. `--qa-job-dir` runs still QA first.
- `master_batch_runner.py --qa-loop` requires policy/requirements/generation graph, then passes receipt flags; without `--qa-loop` it sends `--allow-ungated-i2v` so existing fused batches keep running.
- Tests: `python local_agent/test_gvd_qa_remaining.py`. No GPU models loaded.
