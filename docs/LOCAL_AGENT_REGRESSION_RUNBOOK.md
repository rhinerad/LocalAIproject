# Local Agent regression runbook

Run from the repository root. These checks are deterministic or mocked where
they touch model, GPU, phone, media, or network boundaries; they do not start
ComfyUI, load a model, render, start the Sideband bridge, or submit a worker
job.

## Fast changed-core check

Use after changing the tool loop, router, system prompt, or context handling:

```powershell
python local_agent\test_native_tool_calling.py
python local_agent\test_router_switching.py
python local_agent\validate_h3_prompt.py --dir outputs\equal_shares\prompts_native_r2v
```

Current expected results: 55 native-tool tests, 42 router tests, and
`124/124 valid` prompts.

## Bounded local-agent sweep

The full discovery command can take longer than a short terminal or automation
window. Run these groups from `local_agent\` instead, stopping at the first
failure:

```powershell
cd local_agent
python -m unittest -q test_agentic_eval test_agentic_state test_artifacts test_chat_render_jobs test_chat_retrieval test_context_compactor test_context_prefetch test_context_resilience test_ctx_ceiling test_deep_research
python -m unittest -q test_difficulty test_exemplar_curator test_exemplar_embeddings_concurrency test_exemplar_embeddings test_exemplar_lifecycle test_exemplar_linter test_exemplar_retrieval test_feedback test_general_assistant test_gpu_gate
python -m unittest -q test_gui_render_hint test_h3_evaluation test_launcher_kv_cache test_launcher_revision test_loop_controller test_loop_evaluation test_loop_independent_verifier test_loop_verifiers test_lxmf_bridge test_measure_ollama_kv_cache
python -m unittest -q test_measure_qwen25_vl_lifecycle test_media_analysis test_media_gpu_queue test_media_preemption test_media_watcher_exact_qwen test_memory_extractor test_native_tool_calling test_ollama_context_options test_operating_memory test_operator_eval
python -m unittest -q test_optional_deps test_phone_scheduler test_planner
python -m unittest -q test_powerinfer_chat_route test_powerinfer_openai_proxy test_powerinfer_pipeline test_prompt_prefix test_public_release_audit test_qwen25_release test_qwen25_setup_script
python -m unittest -q test_qwen25_vl_identity test_radio_metrics test_render_story_image test_retrieval_relevance test_router_status_busy test_router_switching test_run_code test_search_backend test_sideband_tier_b test_sonic_pi
python -m unittest -q test_stage_ultrafeedback_eval test_status_cache test_story_image_plan test_story_image_reveal test_subtask_dispatch test_three_d_contract test_three_d_discovery test_verify_qwen25_vl_caption test_vram_arbitration test_workspace_evaluation test_workspace_inspector test_workspace_profiles test_yield_gpu
```

The 2026-09-01 bounded sweep passed 471 local-agent tests.

## Worker-farm suite

Return to the repository root. The farm tests intentionally refuse the normal
interpreter because their isolated environment is part of the security
boundary:

```powershell
cd ..
& .\local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_core local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
```

Expected result: 19 tests passed, with the broker-registration probe skipped
when Celery is not configured in that process.
