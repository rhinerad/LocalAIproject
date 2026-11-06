# Lexical vs Hybrid search_docs — human quality comparison

Judge **which result set would actually answer the question better**,
not only whether the gold chunk id is in top-5.

- chunks: 1040
- embed_mode: live_or_cached  match_by seen: ['both', 'embedding', 'lexical']
- cache coverage after warm: 1.0 (1040/1040)
- farm warm: 0/0 ok in 248.284s
- scoring elapsed: 43.554s

## Mechanical summary (supporting, not the decision)

- gold in search_docs top-5: lexical 12/18, hybrid 13/18
- gold rank ≤5 (raw scorer, before search_relevant filter): lexical 12/18, hybrid 13/18
- identical result sets: 0
- hybrid recovers gold lexical missed: 3
- lexical keeps gold hybrid dropped: 2

## Per-query

### changelog_letter_convention

**Query:** How do parallel agents pick the next changelog filename letter?

**Intent:** 2026-09-02w collision: two agents both chose u. Need YYYY-MM-DDx plus scripts/next_changelog_id.py.

**Gold ids:** `CHANGELOG/2026-09-02w_changelog_letter_convention.md:0`

**Ranks (raw scorer):** lexical=1  hybrid=1  search_docs gold: L=True H=True  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02w_changelog_letter_convention.md:0` **GOLD**  
   match_by=lexical score=30.1573  
   # 2026-09-02w — changelog letter allocation for parallel agents  
   # 2026-09-02w — changelog letter allocation for parallel agents ## What `2026-09-02u_farm_status_daemon.md` was renamed to `2026-09-02v_farm_status_daemon.md` so it no longer collides with `2026-09-02u_compaction_prefetch.md` (two agents independently chose `u` the same day). First-come kept `u`. ## Convention Changelog entries are `YYYY-MM-DDx_description.md` with a sequential letter `x`. Before naming one, check `…

2. `CLAUDE.md:1`  
   match_by=lexical score=23.9939  
   ## SCOPE NOTICE — 2026-08-30, read this before anything below  
   low; do not treat its Equal Shares soundtrack job description or its "keep going until the audio gate passes" persistence language as current instructions to resume that work. Everything below this notice was written before the reprioritization and is preserved for the safety rules it contains and for anyone doing deliberate, explicitly-requested Equal Shares work later. ## READ FIRST — two folders that override eve…

3. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:15`  
   match_by=lexical score=15.4928  
   ## Execution gates (open items that need operator input)  
   gated behind operator prioritization against everything else here, not a hard blocker `docs/LOCAL_AGENT_OPERATOR_DECISIONS.md` turns these gates into a single concise response template; it is documentation only and grants no capability. No background worker, phone, renderer, ComfyUI instance, or PowerInfer process may be started merely to clear an unchecked box. --- ## Full CHANGELOG index for 2026-09-02 For referen…

4. `CHANGELOG/2026-09-03ak_farm_dashboard_degraded_alert.md:0`  
   match_by=lexical score=14.7463  
   # 2026-09-03ak — farm dashboard degraded-health alert  
   # 2026-09-03ak — farm dashboard degraded-health alert Follow-up to `2026-09-03n` (dashboard) and `2026-09-03v` (phone reached). Letter reconfirmed with `python scripts/next_changelog_id.py` immediately before this file (`aj` already taken by three parallel entries). ## What Lightweight alert when the LAN dashboard sees the farm as not healthy. Stdlib only. No new dependencies. No second health definition. Degraded =…

5. `CHANGELOG/2026-09-03h_session_handoff.md:1`  
   match_by=lexical score=11.1061  
   ## 2. Code & Architecture Changes  
   . * TurboSparse (GPU go, convert/quantize/package/bench only; no dump/train): Q4 GGUF built from `turbosparse-approved-20260902-182522`; 20/20 cold+warm mechanical gate pass; agentic quality gate **failed_turn_1** (`invalid_json`); production registry **refused**. Evidence: `CHANGELOG/2026-09-03b_turbosparse_approved_convert_bench.md`. Parked `20260830b` tree untouched. ## 3. Pending Items / Next Steps * Restore Mac…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02w_changelog_letter_convention.md:0` **GOLD**  
   match_by=both score=0.0328  
   # 2026-09-02w — changelog letter allocation for parallel agents  
   # 2026-09-02w — changelog letter allocation for parallel agents ## What `2026-09-02u_farm_status_daemon.md` was renamed to `2026-09-02v_farm_status_daemon.md` so it no longer collides with `2026-09-02u_compaction_prefetch.md` (two agents independently chose `u` the same day). First-come kept `u`. ## Convention Changelog entries are `YYYY-MM-DDx_description.md` with a sequential letter `x`. Before naming one, check `…

2. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:15`  
   match_by=both score=0.0317  
   ## Execution gates (open items that need operator input)  
   gated behind operator prioritization against everything else here, not a hard blocker `docs/LOCAL_AGENT_OPERATOR_DECISIONS.md` turns these gates into a single concise response template; it is documentation only and grants no capability. No background worker, phone, renderer, ComfyUI instance, or PowerInfer process may be started merely to clear an unchecked box. --- ## Full CHANGELOG index for 2026-09-02 For referen…

3. `CHANGELOG/README.md:0`  
   match_by=both score=0.0291  
   # CHANGELOG â€” every change to this project, in detail, no exceptions  
   # CHANGELOG â€” every change to this project, in detail, no exceptions Filenames are `YYYY-MM-DD` + sequential letter + `_slug.md`. Run `python scripts/next_changelog_id.py` for the next free id. # 2026-09-03 — [HARNESS_OPTIMIZATION.md §4a marked implemented](2026-09-03ax_harness_4a_implemented.md) # 2026-09-03 — [agent.py farm-routing caller: farm_status.json gate, prefetch-only summarize](2026-09-03aw_farm_routing…

4. `docs/hybrid_scorer_proposal.md:3`  
   match_by=both score=0.0284  
   ## Risks (why this is still gated)  
   model and is not concurrency-safe — do not silently hang a CE on that path either without approval. 3. **No farm rerank queue.** Embed and summarize already offload. There is no rerank Celery task and this proposal does not add one. If approved, rerank runs on **local workstation CPU only**. Do not touch `farm_offload.py`, `agent.py`, or `worker_farm/` files. ## Implementation steps (after approval only) For another…

5. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1`  
   match_by=both score=0.0258  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

---

### source_citation_contract

**Query:** What must a factual claim from project documents cite?

**Intent:** Agent citation rules: path and heading, not a generic 'cite sources' lecture.

**Gold ids:** `CHANGELOG/2026-09-02b_source_citation_contract.md:0`

**Ranks (raw scorer):** lexical=1  hybrid=1  search_docs gold: L=True H=True  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02b_source_citation_contract.md:0` **GOLD**  
   match_by=lexical score=22.534  
   # 2026-09-02b — Source citation contract for factual claims  
   # 2026-09-02b — Source citation contract for factual claims ## What changed The local agent now requires source-backed factual claims and preserves provenance through context pruning. ## Files modified ### `local_agent/agent.py` - Added `# Source citation` section to `CONVERSATION_RULES` (between the tool-mechanics silence rule and the scoped-project-docs rule). Contract: - **Web / internet** claims must include the…

2. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:9`  
   match_by=lexical score=20.7847  
   ### `LLMOPS_AUDIT.md` — audit + spec, no code  
   pre-score tracked for correlation against human scores, never auto-accepted; (c) Reason→Act→Observe pseudocode with tracing spans. One concrete required code change identified but not yet made: stop discarding those token/duration fields. New `TODO.md` "LLMOps / observability" section with 3 tracked items, all unimplemented. (`CHANGELOG/2026-09-02p_llmops_audit_spec.md`) ### Source citation contract The agent now re…

3. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md:6`  
   match_by=lexical score=18.0815  
   ### Action-resolution layer  
   five reported failure patterns are now covered by regression tests in `test_action_resolver.py` (29 tests total). The 57-test `test_native_tool_calling.py` suite passes without regressions. `APP_REVISION` is `2026-09-01-action-resolver-r76`; the launcher `START_LOCAL_AGENT_GUI.ps1` expects the same revision. No GPU, render, model load, or PowerInfer process was started. ### Source citation contract The agent now req…

4. `local_agent/UPGRADE/02_context_and_retrieval.md:0`  
   match_by=lexical score=11.7434  
   # Claude Code prompt — retrieval over the whole doc tree (refreshed 2026-08-23)  
   # Claude Code prompt — retrieval over the whole doc tree (refreshed 2026-08-23) Paste into your coding agent. Run from the repo root (`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/README.md`, `CLAUDE.md`, `local_agent/agent.py`, and `local_agent/router.py` first. ## What this is (and what already changed since the original 02) The original upgrade 2 had two halves. **Half one — raising `num_ctx` — is alrea…

5. `local_agent/UPGRADE/16_agentic_reasoning_execution_loop.md:1`  
   match_by=lexical score=10.6976  
   ### Stage 1 — implemented 2026-08-24  
   it is not a second model silently judging its own output. Casual chat does not create a task plan, and a new substantial task replaces the prior checkpoint for that conversation. No packages were downloaded. Native Ollama schemas remain the function protocol; `tools.py`, remote default-deny, render preflight, protected-file checks, and localhost-only HTTP are unchanged. ### Stage 2 — implemented 2026-08-24 The harne…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02b_source_citation_contract.md:0` **GOLD**  
   match_by=both score=0.0328  
   # 2026-09-02b — Source citation contract for factual claims  
   # 2026-09-02b — Source citation contract for factual claims ## What changed The local agent now requires source-backed factual claims and preserves provenance through context pruning. ## Files modified ### `local_agent/agent.py` - Added `# Source citation` section to `CONVERSATION_RULES` (between the tool-mechanics silence rule and the scoped-project-docs rule). Contract: - **Web / internet** claims must include the…

2. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:9`  
   match_by=both score=0.0315  
   ### `LLMOPS_AUDIT.md` — audit + spec, no code  
   pre-score tracked for correlation against human scores, never auto-accepted; (c) Reason→Act→Observe pseudocode with tracing spans. One concrete required code change identified but not yet made: stop discarding those token/duration fields. New `TODO.md` "LLMOps / observability" section with 3 tracked items, all unimplemented. (`CHANGELOG/2026-09-02p_llmops_audit_spec.md`) ### Source citation contract The agent now re…

3. `local_agent/UPGRADE/02_context_and_retrieval.md:1`  
   match_by=both score=0.0313  
   ## Job 2 — expose it as a tool  
   heading** so the agent can cite where a claim came from — a claim without a source is not evidence in this project. It is a read-only tool; it never writes. Update `CONVERSATION_RULES` in `agent.py`: for any question about a rule, a decision, why something is the way it is, or project history — **search the docs first**; `read_doc` stays for reading a whole named file. ## Job 3 — shrink the compiled brief Now that r…

4. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-01.md:6`  
   match_by=both score=0.03  
   ### Action-resolution layer  
   five reported failure patterns are now covered by regression tests in `test_action_resolver.py` (29 tests total). The 57-test `test_native_tool_calling.py` suite passes without regressions. `APP_REVISION` is `2026-09-01-action-resolver-r76`; the launcher `START_LOCAL_AGENT_GUI.ps1` expects the same revision. No GPU, render, model load, or PowerInfer process was started. ### Source citation contract The agent now req…

5. `docs/GOOGLE_DRIVE_PROJECT_SOURCE_INDEX.md:0`  
   match_by=both score=0.0287  
   # Google Drive Project Source Index  
   # Google Drive Project Source Index Last inventoried: 2026-08-24 (America/New_York). This is a source map, not a replacement for the project documentation that is already checked into this handoff. It records the project-scoped Google Drive documents discovered through the connected Drive and the date rule used when their guidance overlaps. ## Authority and date rule 1. Safety constraints in `CLAUDE.md`, the live ha…

---

### hybrid_is_default

**Query:** Is FlashRank the default docs search now?

**Intent:** Default is HybridScorer; FlashRank was deferred and not installed.

**Gold ids:** `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:0`, `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1`

**Ranks (raw scorer):** lexical=2  hybrid=5  search_docs gold: L=True H=True  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=lexical score=18.861  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

2. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1` **GOLD**  
   match_by=lexical score=17.8349  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

3. `docs/hybrid_scorer_proposal.md:2`  
   match_by=lexical score=17.6482  
   ## Sketch — wrap Hybrid, do not flip the default  
   ports with no new packages installed. - Fallback on `ImportError` (and treat ranker runtime errors the same way Hybrid treats a dead embedding endpoint): return the inner Hybrid ranking; do not fail `search_docs`. - Preserve `_match_by` on the shallow-copied chunks Hybrid already tags. Do not mutate index chunks. - **Do not flip `_DEFAULT_SCORER`.** Callers opt in: `search(q, scorer=RerankedScorer())`. `search_docs`…

4. `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md:0`  
   match_by=lexical score=17.3728  
   # 2026-09-03ae — RAG Stage 3 FlashRank close-call (not implemented)  
   # 2026-09-03ae — RAG Stage 3 FlashRank close-call (not implemented) Re-read live `local_agent/retrieval.py` and the Phase 2 / Stage 3 outline (`TODO.md` item 4, `RAG_EVALUATION.md`, `docs/hybrid_scorer_proposal.md`). Did not treat 2026-09-02m / 2026-09-02ab as current state. **Decision: not a clear win. Keep `HybridScorer` as `_DEFAULT_SCORER`. Do not pip-install FlashRank. Do not add `RerankedScorer`.** ## What is …

5. `docs/hybrid_scorer_proposal.md:0`  
   match_by=lexical score=17.031  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal **Status: proposal only. 2026-09-03ae close-call — do not implement. Keep HybridScorer as default.** Research is done. This is a short handoff for another agent. Nothing here authorizes installing packages, flipping `_DEFAULT_SCORER`, or editing `local_agent/retrieval.py`. Stage 3 stays deferred until the operator names the new dependency in an explici…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.0323  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

2. `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md:0`  
   match_by=both score=0.032  
   # 2026-09-03ae — RAG Stage 3 FlashRank close-call (not implemented)  
   # 2026-09-03ae — RAG Stage 3 FlashRank close-call (not implemented) Re-read live `local_agent/retrieval.py` and the Phase 2 / Stage 3 outline (`TODO.md` item 4, `RAG_EVALUATION.md`, `docs/hybrid_scorer_proposal.md`). Did not treat 2026-09-02m / 2026-09-02ab as current state. **Decision: not a clear win. Keep `HybridScorer` as `_DEFAULT_SCORER`. Do not pip-install FlashRank. Do not add `RerankedScorer`.** ## What is …

3. `docs/hybrid_scorer_proposal.md:2`  
   match_by=both score=0.0315  
   ## Sketch — wrap Hybrid, do not flip the default  
   ports with no new packages installed. - Fallback on `ImportError` (and treat ranker runtime errors the same way Hybrid treats a dead embedding endpoint): return the inner Hybrid ranking; do not fail `search_docs`. - Preserve `_match_by` on the shallow-copied chunks Hybrid already tags. Do not mutate index chunks. - **Do not flip `_DEFAULT_SCORER`.** Callers opt in: `search(q, scorer=RerankedScorer())`. `search_docs`…

4. `docs/hybrid_scorer_proposal.md:0`  
   match_by=both score=0.0308  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal **Status: proposal only. 2026-09-03ae close-call — do not implement. Keep HybridScorer as default.** Research is done. This is a short handoff for another agent. Nothing here authorizes installing packages, flipping `_DEFAULT_SCORER`, or editing `local_agent/retrieval.py`. Stage 3 stays deferred until the operator names the new dependency in an explici…

5. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1` **GOLD**  
   match_by=both score=0.0296  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

---

### flashrank_catalog_names

**Query:** Which FlashRank model names are actually in the catalog?

**Intent:** TinyBERT-L-2-v2 and MiniLM-L-12-v2. L-6-v2 is not in the catalog — 2026-09-02m named it wrongly.

**Gold ids:** `CHANGELOG/2026-09-03c_docs_flashrank_todo_arch.md:0`, `docs/hybrid_scorer_proposal.md:1`

**Ranks (raw scorer):** lexical=2  hybrid=1  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `docs/hybrid_scorer_proposal.md:0`  
   match_by=lexical score=18.2589  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal **Status: proposal only. 2026-09-03ae close-call — do not implement. Keep HybridScorer as default.** Research is done. This is a short handoff for another agent. Nothing here authorizes installing packages, flipping `_DEFAULT_SCORER`, or editing `local_agent/retrieval.py`. Stage 3 stays deferred until the operator names the new dependency in an explici…

2. `CHANGELOG/2026-09-03c_docs_flashrank_todo_arch.md:0` **GOLD**  
   match_by=lexical score=17.7262  
   # Docs-only: FlashRank catalog names, Swarm checkbox rollup, ARCHITECTURE re-read  
   # Docs-only: FlashRank catalog names, Swarm checkbox rollup, ARCHITECTURE re-read Date: 2026-09-03. Docs only; no code changed. ## What changed - `TODO.md` Phase 2 item 4 Stage 3 and `RAG_EVALUATION.md` open question 1 no longer name `ms-marco-MiniLM-L-6-v2` as a FlashRank model. Catalog-correct options are `ms-marco-TinyBERT-L-2-v2` (default) and `ms-marco-MiniLM-L-12-v2` (larger). See `docs/hybrid_scorer_proposal.…

3. `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md:2`  
   match_by=lexical score=16.1746  
   ## Latency and footprint  
   extra search latency; not fine as a silent ~0.5 GiB residency on a tool that is in `CONCURRENCY_SAFE_TOOLS` (ONNX sessions are not automatically thread-safe). Install if we did it: `pip install flashrank` (depends on onnxruntime, already here) + first-use download of TinyBERT. No torch. MiniLM-L-12-v2 (~34 MB) is the catalog quality fallback and is several times slower. ## Why this stays a close call For: - onnxrunt…

4. `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md:1`  
   match_by=lexical score=16.1284  
   ## What is true on disk today  
   omadb` for exemplar retrieval). `tokenizers`, `numpy`, `requests`, `tqdm` are already present. `torch` is not. The 2026-09-02ab "new onnxruntime runtime, same bar as PowerInfer" reason is **stale for this interpreter**. The remaining costs are FlashRank itself (~14 KB wheel), the TinyBERT ONNX (~5 MB), Ranker RSS, truncation, and unmeasured quality on *this* corpus. ## Accuracy (published, not this corpus) There is …

5. `docs/hybrid_scorer_proposal.md:1` **GOLD**  
   match_by=lexical score=13.3319  
   ## Models (correct the 2026-09-02m pick)  
   alling L-6-v2. Do not add a custom ONNX of it. | Role | FlashRank id | Size | Notes | |---|---|---|---| | Default / first | `ms-marco-TinyBERT-L-2-v2` | ~4 MB | FlashRank's own default. Start here. | | Quality fallback | `ms-marco-MiniLM-L-12-v2` | ~34 MB | Pairwise catalog model. Opt-in only if TinyBERT quality is insufficient. | Do not ship L-12 as the first install. ## Sketch — wrap Hybrid, do not flip the defaul…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-03c_docs_flashrank_todo_arch.md:0` **GOLD**  
   match_by=both score=0.0325  
   # Docs-only: FlashRank catalog names, Swarm checkbox rollup, ARCHITECTURE re-read  
   # Docs-only: FlashRank catalog names, Swarm checkbox rollup, ARCHITECTURE re-read Date: 2026-09-03. Docs only; no code changed. ## What changed - `TODO.md` Phase 2 item 4 Stage 3 and `RAG_EVALUATION.md` open question 1 no longer name `ms-marco-MiniLM-L-6-v2` as a FlashRank model. Catalog-correct options are `ms-marco-TinyBERT-L-2-v2` (default) and `ms-marco-MiniLM-L-12-v2` (larger). See `docs/hybrid_scorer_proposal.…

2. `docs/hybrid_scorer_proposal.md:1` **GOLD**  
   match_by=both score=0.0313  
   ## Models (correct the 2026-09-02m pick)  
   alling L-6-v2. Do not add a custom ONNX of it. | Role | FlashRank id | Size | Notes | |---|---|---|---| | Default / first | `ms-marco-TinyBERT-L-2-v2` | ~4 MB | FlashRank's own default. Start here. | | Quality fallback | `ms-marco-MiniLM-L-12-v2` | ~34 MB | Pairwise catalog model. Opt-in only if TinyBERT quality is insufficient. | Do not ship L-12 as the first install. ## Sketch — wrap Hybrid, do not flip the defaul…

3. `docs/hybrid_scorer_proposal.md:0`  
   match_by=both score=0.0309  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal  
   # Stage 3 — RerankedScorer (FlashRank) — implementation proposal **Status: proposal only. 2026-09-03ae close-call — do not implement. Keep HybridScorer as default.** Research is done. This is a short handoff for another agent. Nothing here authorizes installing packages, flipping `_DEFAULT_SCORER`, or editing `local_agent/retrieval.py`. Stage 3 stays deferred until the operator names the new dependency in an explici…

4. `docs/hybrid_scorer_proposal.md:4`  
   match_by=both score=0.0303  
   ## Citations  
   ault.md` — Hybrid is default; FlashRank/onnxruntime explicitly not installed ## Addendum — TinyBERT local-CPU cost (2026-09-03) Research-only. No package was added to the workstation agent env, and `retrieval.py` was not edited. This bounds the "workstation-CPU-sized" claim in Risks item 2 for the proposed default `ms-marco-TinyBERT-L-2-v2` at fused top-N 20 and 50. ### Published numbers - HuggingFace `cross-encoder…

5. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.03  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

---

### search_docs_thread_safety

**Query:** Why can search_docs run from several threads in the same hop?

**Intent:** CONCURRENCY_SAFE_TOOLS plus the unlocked _INDEX_CACHE race that 2026-08-31d fixed.

**Gold ids:** `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:0`

**Ranks (raw scorer):** lexical=1  hybrid=1  search_docs gold: L=True H=True  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:0` **GOLD**  
   match_by=lexical score=27.8073  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution ## What changed Found during a follow-up audit of the same-day parallel-tool-execution change (`CHANGELOG/2026-08-31c_...md`), specifically auditing every tool newly reachable from concurrent threads for thread-safety. `retrieval._get_index()` did an unlocked check-then-build on the module-level `_INDEX_CACHE` global: ```…

2. `CHANGELOG/2026-08-31c_parallel_tools_subagent_dispatch_thread_cap_consolidation.md:0`  
   match_by=lexical score=18.8026  
   # 2026-08-31 — parallel tool execution, a bounded sub-agent primitive, and CPU thread-cap consolidation  
   # 2026-08-31 — parallel tool execution, a bounded sub-agent primitive, and CPU thread-cap consolidation ## What changed Three follow-ups from an architecture-vs-standard-agent-harness comparison (and its own follow-up safety-invariant audit). One additional item from that same audit (protected-file scoping) was reviewed and deliberately left unchanged — see the end of this entry. **1. Parallel tool execution within …

3. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=lexical score=14.2321  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

4. `CHANGELOG/2026-09-03ad_unguarded_answer_path_tool_exceptions.md:1`  
   match_by=lexical score=13.9787  
   ### Already guarded (left unchanged)  
   )` `clip_info`** — not inside `answer()`; a separate drafting API. Left as-is (supposed to surface to that caller). 12. **`lxmf_agent` schedule-cancel `tools.call`** — phone fast-path, not `answer()` hop-loop. Left as-is. 13. **No computer-use / second hop-loop copy** in `agent.py`. Native and legacy (`TOOL:` text) both feed the same guarded `hop_calls` / `run_one` loop. ### Newly wrapped (same ERROR pattern) 14. **…

5. `CHANGELOG/2026-08-23_retrieval_over_tree.md:0`  
   match_by=lexical score=13.8876  
   # 2026-08-23 — UPGRADE 02 (retrieval half): BM25 search over the document tree  
   # 2026-08-23 — UPGRADE 02 (retrieval half): BM25 search over the document tree ## What changed ### local_agent/retrieval.py (new) - stdlib-only BM25 retrieval. No rank_bm25, no sklearn, no downloads. - `LexicalScorer` — 35-line BM25 (K1=1.5, b=0.75). Swappable via `ScorerProtocol`. - `EmbeddingScorer` — stub placeholder for UPGRADE 05's embedding model. - Indexes 77 files across `docs/**/*.md`, `CLAUDE.md`, `README.…

**Hybrid search_docs**

1. `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:0` **GOLD**  
   match_by=both score=0.0328  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution ## What changed Found during a follow-up audit of the same-day parallel-tool-execution change (`CHANGELOG/2026-08-31c_...md`), specifically auditing every tool newly reachable from concurrent threads for thread-safety. `retrieval._get_index()` did an unlocked check-then-build on the module-level `_INDEX_CACHE` global: ```…

2. `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:1`  
   match_by=both score=0.0308  
   ## Fix  
   dex()` now does proper double-checked locking (fast unlocked read when the cache is warm, lock-protected check-and-build when cold), and `rebuild()` wraps its reset-and-rebuild in the same lock, so a sequential `run_build("rebuild")` call and concurrent `search_docs` calls always serialize against each other rather than racing on `_INDEX_CACHE` or the on-disk index file. ## What was verified - `python3 -m py_compile…

3. `CHANGELOG/2026-08-31c_parallel_tools_subagent_dispatch_thread_cap_consolidation.md:0`  
   match_by=both score=0.0306  
   # 2026-08-31 — parallel tool execution, a bounded sub-agent primitive, and CPU thread-cap consolidation  
   # 2026-08-31 — parallel tool execution, a bounded sub-agent primitive, and CPU thread-cap consolidation ## What changed Three follow-ups from an architecture-vs-standard-agent-harness comparison (and its own follow-up safety-invariant audit). One additional item from that same audit (protected-file scoping) was reviewed and deliberately left unchanged — see the end of this entry. **1. Parallel tool execution within …

4. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.0306  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

5. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`  
   match_by=both score=0.0297  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

---

### agentic_search_not_concurrency_safe

**Query:** Is agentic_search_docs safe to run in parallel with search_docs?

**Intent:** Separate tool, PROJECT_ONLY_TOOLS, not CONCURRENCY_SAFE_TOOLS because it calls the model.

**Gold ids:** `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1`, `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:1`

**Ranks (raw scorer):** lexical=1  hybrid=3  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1` **GOLD**  
   match_by=lexical score=30.078  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

2. `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:0`  
   match_by=lexical score=25.6686  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution ## What changed Found during a follow-up audit of the same-day parallel-tool-execution change (`CHANGELOG/2026-08-31c_...md`), specifically auditing every tool newly reachable from concurrent threads for thread-safety. `retrieval._get_index()` did an unlocked check-then-build on the module-level `_INDEX_CACHE` global: ```…

3. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:7`  
   match_by=lexical score=24.9641  
   ### RAG upgrade — Stages 1, 2, and 4 implemented and test-verified; Stage 3 researched only  
   esult itself is recorded twice independently and both agree): `agentic_retrieval.py` / `agentic_search_docs()`, a bounded retrieve→grade→retry loop mirroring `deep_research.py`'s pattern (`MAX_SUBQUERIES=4`/round, `MAX_ROUNDS=3`, dedup against tried queries). Uses `HybridScorer`; the model self-grades sufficiency via trailing JSON; includes an anti-hallucination guard that strips/rejects fabricated file-path citatio…

4. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:1` **GOLD**  
   match_by=lexical score=24.7356  
   ## Wiring  
   ded to `CONCURRENCY_SAFE_TOOLS`** — it calls the model, same reason `deep_research` is excluded. - New JSON schema entry for native tool-calling, `required: ["question"]`. This is additive only — the existing `search_docs` tool, its lexical-only `search_relevant()` grader, and `HybridScorer`'s non-default status are all unchanged. No default behavior anywhere changed. ## Tests — written, NOT yet executed `local_agen…

5. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`  
   match_by=lexical score=23.717  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

**Hybrid search_docs**

1. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:7`  
   match_by=both score=0.0323  
   ### RAG upgrade — Stages 1, 2, and 4 implemented and test-verified; Stage 3 researched only  
   esult itself is recorded twice independently and both agree): `agentic_retrieval.py` / `agentic_search_docs()`, a bounded retrieve→grade→retry loop mirroring `deep_research.py`'s pattern (`MAX_SUBQUERIES=4`/round, `MAX_ROUNDS=3`, dedup against tried queries). Uses `HybridScorer`; the model self-grades sufficiency via trailing JSON; includes an anti-hallucination guard that strips/rejects fabricated file-path citatio…

2. `CHANGELOG/2026-08-31d_search_docs_index_cache_race.md:0`  
   match_by=both score=0.0318  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution  
   # 2026-08-31 — retrieval.py: search_docs index-cache race introduced by parallel tool execution ## What changed Found during a follow-up audit of the same-day parallel-tool-execution change (`CHANGELOG/2026-08-31c_...md`), specifically auditing every tool newly reachable from concurrent threads for thread-safety. `retrieval._get_index()` did an unlocked check-then-build on the module-level `_INDEX_CACHE` global: ```…

3. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:1` **GOLD**  
   match_by=both score=0.0318  
   ## Wiring  
   ded to `CONCURRENCY_SAFE_TOOLS`** — it calls the model, same reason `deep_research` is excluded. - New JSON schema entry for native tool-calling, `required: ["question"]`. This is additive only — the existing `search_docs` tool, its lexical-only `search_relevant()` grader, and `HybridScorer`'s non-default status are all unchanged. No default behavior anywhere changed. ## Tests — written, NOT yet executed `local_agen…

4. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`  
   match_by=both score=0.0313  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

5. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1` **GOLD**  
   match_by=both score=0.0311  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

---

### agentic_retry_loop

**Query:** What local-docs tool retries with rewritten queries when the first hits are weak?

**Intent:** agentic_search_docs: retrieve, model-grade, retry up to MAX_ROUNDS=3, strip invented citations.

**Gold ids:** `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`

**Ranks (raw scorer):** lexical=2  hybrid=1  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `CHANGELOG/2026-09-03ae_flashrank_stage3_close_call.md:1`  
   match_by=lexical score=21.1675  
   ## What is true on disk today  
   omadb` for exemplar retrieval). `tokenizers`, `numpy`, `requests`, `tqdm` are already present. `torch` is not. The 2026-09-02ab "new onnxruntime runtime, same bar as PowerInfer" reason is **stale for this interpreter**. The remaining costs are FlashRank itself (~14 KB wheel), the TinyBERT ONNX (~5 MB), Ranker RSS, truncation, and unmeasured quality on *this* corpus. ## Accuracy (published, not this corpus) There is …

2. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0` **GOLD**  
   match_by=lexical score=21.0894  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

3. `CHANGELOG/2026-08-18_duration_ladder.md:0`  
   match_by=lexical score=14.1786  
   # 2026-08-18 — the duration ladder becomes the retry rule  
   # 2026-08-18 — the duration ladder becomes the retry rule ## What changed The retry knob for bad speech is now the **duration**, not the seed. Operator instruction, verbatim: > "when generating audio and trying to get perfect English words (getting rid of > gibberish or mispronounced words) use this generation pattern. Example start at > 10 sec; if gen is bad (has mispronounced words) add a second. If that does not …

4. `CHANGELOG/2026-09-03ai_timing_assertion_audit.md:0`  
   match_by=lexical score=14.1056  
   # 2026-09-03ai — Timing-assertion audit (no code change)  
   # 2026-09-03ai — Timing-assertion audit (no code change) Follow-up to `2026-09-03ag_parallel_hop_timing_assertion.md`. Searched every `test_*.py` under `local_agent/`, `local_agent/worker_farm/`, `work/`, and `tools/powerinfer/` for wall-clock concurrency/performance assertions (`time.monotonic`, `perf_counter`, `assertLess(elapsed, …)`). Did not change production or test code: the only same-class failure was the on…

5. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:1`  
   match_by=lexical score=13.9753  
   ## Wiring  
   ded to `CONCURRENCY_SAFE_TOOLS`** — it calls the model, same reason `deep_research` is excluded. - New JSON schema entry for native tool-calling, `required: ["question"]`. This is additive only — the existing `search_docs` tool, its lexical-only `search_relevant()` grader, and `HybridScorer`'s non-default status are all unchanged. No default behavior anywhere changed. ## Tests — written, NOT yet executed `local_agen…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0` **GOLD**  
   match_by=both score=0.0318  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

2. `CHANGELOG/2026-09-01_execution_first_retry_and_status_lock.md:0`  
   match_by=both score=0.0304  
   # 2026-09-01 — Execution-first retry and Windows status-marker lock tolerance  
   # 2026-09-01 — Execution-first retry and Windows status-marker lock tolerance ## Operator outcome For a direct desktop request to carry out safe work, the local agent now makes one bounded corrective model turn when the first reply only gives the operator instructions and no tool has been attempted. The correction directs the model to select and use the appropriate available tool, then report the result or a specifi…

3. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:1`  
   match_by=both score=0.0299  
   ## Stage 5 cheap comparison (this session, not a large eval)  
   026-09-01.md`, `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md`, `CHANGELOG/2026-09-02b_source_citation_contract.md` - `changelog letter convention` → `CHANGELOG/2026-09-02w_changelog_letter_convention.md` - `farm status snapshot daemon` → `CHANGELOG/2026-09-02v_farm_status_daemon.md` A larger hand-judged query set remains an operator lever, not a block. ## What was wired Smallest default-behavior change that does n…

4. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:1`  
   match_by=both score=0.0285  
   ## Wiring  
   ded to `CONCURRENCY_SAFE_TOOLS`** — it calls the model, same reason `deep_research` is excluded. - New JSON schema entry for native tool-calling, `required: ["question"]`. This is additive only — the existing `search_docs` tool, its lexical-only `search_relevant()` grader, and `HybridScorer`'s non-default status are all unchanged. No default behavior anywhere changed. ## Tests — written, NOT yet executed `local_agen…

5. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.0282  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

---

### farm_status_snapshot

**Query:** Where can I read farm worker liveness without calling Celery inspect live?

**Intent:** farm_status.json snapshot daemon, not a live inspect() on every read.

**Gold ids:** `CHANGELOG/2026-09-02v_farm_status_daemon.md:0`

**Ranks (raw scorer):** lexical=3  hybrid=1  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `docs/RUNBOOK.md:1`  
   match_by=lexical score=22.2358  
   ## 0. Is this the workstation, or the farm?  
   (LAN IP tonight: `192.168.50.8`.) 3. From that Mac shell, ping/TCP the hub yourself (`10.90.90.1:6379`). 4. Only if LAN SSH also fails is the Mac actually down. Otherwise keep going — the farm process may be fine and the tunnel/path is the bug. Trap: the workstation's own connection flaking looks identical to "Redis is down" or "no workers" in `farm_health`. --- ## 1. Connectivity is not task availability `farm_heal…

2. `CHANGELOG/2026-09-02t_farm_health.md:0`  
   match_by=lexical score=19.8773  
   # 2026-09-02t — standalone farm_health diagnostic  
   # 2026-09-02t — standalone farm_health diagnostic ## What Added `local_agent/worker_farm/farm_health.py`: a CLI + `check_farm_health(timeout_s=5.0)` helper that reports broker reachable / workers responding / latency_ms without submitting any summarize, embed, judge, or distill job. ## How it checks 1. Loads `local_agent/worker_farm/.env` the same way `_farm_submit_wait._load_env_file` does (does not override alread…

3. `CHANGELOG/2026-09-02v_farm_status_daemon.md:0` **GOLD**  
   match_by=lexical score=19.6384  
   # 2026-09-02v — farm_status.json snapshot daemon  
   # 2026-09-02v — farm_status.json snapshot daemon ## What Periodic cheap farm-status snapshot on top of `farm_health.check_farm_health()`. Other code can read `local_agent/worker_farm/farm_status.json` instead of calling Celery `inspect()` live. Not wired into `agent.py` or `farm_offload.py`. ## farm_health --json `--json` already existed. It now stamps `checked_at` (UTC ISO-8601) onto the same object `check_farm_hea…

4. `CHANGELOG/2026-09-02ab_phase2_hybrid_default.md:0`  
   match_by=lexical score=18.6717  
   # 2026-09-02ab — Phase 2 RAG: FlashRank deferred; HybridScorer default  
   # 2026-09-02ab — Phase 2 RAG: FlashRank deferred; HybridScorer default ## FlashRank / Stage 3 — explicit deferral (nothing installed) Decision this session: **do not add FlashRank, onnxruntime, or `ms-marco-MiniLM-L-6-v2`.** That is a new runtime dependency, same bar as PowerInfer / TinyChatEngine. Stage 4 already gives a HybridScorer-backed path via `agentic_search_docs`. Stage 3 can wait for a later explicit new-d…

5. `docs/FARM_HEALTH_RUNBOOK.md:1`  
   match_by=lexical score=18.2907  
   ## 1. Health check (workstation, farm venv, repo root)  
   responding: no latency_ms: 1479.6 error: broker reachable, no worker answered ping registered-task status: no_workers workers: (none) registered: (none) missing_expected: ...connectivity_probe, ...judge_transcript, ...summarize_conversation, ...embed_chunks ``` Windows hub was up. Cached `farm_status.json` last healthy 4:45:56 PM ET — do not trust a stale snapshot. ## 2. Registered-task check (same CLI, added tonigh…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02v_farm_status_daemon.md:0` **GOLD**  
   match_by=both score=0.032  
   # 2026-09-02v — farm_status.json snapshot daemon  
   # 2026-09-02v — farm_status.json snapshot daemon ## What Periodic cheap farm-status snapshot on top of `farm_health.check_farm_health()`. Other code can read `local_agent/worker_farm/farm_status.json` instead of calling Celery `inspect()` live. Not wired into `agent.py` or `farm_offload.py`. ## farm_health --json `--json` already existed. It now stamps `checked_at` (UTC ISO-8601) onto the same object `check_farm_hea…

2. `CHANGELOG/2026-09-02t_farm_health.md:0`  
   match_by=both score=0.032  
   # 2026-09-02t — standalone farm_health diagnostic  
   # 2026-09-02t — standalone farm_health diagnostic ## What Added `local_agent/worker_farm/farm_health.py`: a CLI + `check_farm_health(timeout_s=5.0)` helper that reports broker reachable / workers responding / latency_ms without submitting any summarize, embed, judge, or distill job. ## How it checks 1. Loads `local_agent/worker_farm/.env` the same way `_farm_submit_wait._load_env_file` does (does not override alread…

3. `docs/ARCHITECTURE.md:0`  
   match_by=both score=0.0313  
   # Worker farm architecture (current state)  
   # Worker farm architecture (current state) Written 2026-09-02 from source (`agent.py`, `farm_offload.py`, `compaction_prefetch.py`, `retrieval.py`, `worker_farm/tasks.py`, `celery_app.py`, `farm_health.py`, `farm_status_daemon.py`) plus same-day farm changelogs. Routing/health-gate re-read 2026-09-03 evening against `farm_offload.should_route` and `agent._maybe_start_farm_summary_prefetch` (`CHANGELOG/2026-09-03aw_f…

4. `docs/FARM_HEALTH_RUNBOOK.md:0`  
   match_by=both score=0.0301  
   # Farm health runbook  
   # Farm health runbook Date: 2026-09-03. Diagnostic sequence from 2026-09-02 evening through ~2:55 AM ET. **Reboot persistence is not confirmed.** ## Trap Interface-up ≠ datapath. Windows hub and Mac `utun5` / `10.90.90.2` can both look Connected while Redis / SSH / ICMP over `10.90.90.0/28` are dead. Hot path: `farm_offload.farm_reachable()` reads `farm_status.json` with the same overall-healthy rule as the dashboar…

5. `CHANGELOG/2026-09-03n_farm_status_dashboard.md:0`  
   match_by=both score=0.0257  
   # 2026-09-03n — farm status dashboard (LAN :8765)  
   # 2026-09-03n — farm status dashboard (LAN :8765) Stdlib-only local farm monitoring dashboard on DuranGamingPC. ## What - `local_agent/worker_farm/dashboard/` — `server.py` (system Python + `ThreadingHTTPServer`), `collect.py` (poll helpers), `index.html` (dark ops UI), `Start-FarmDashboard.ps1`. - Binds **private LAN IPv4 only** (detect via `Get-NetIPAddress`; never `0.0.0.0`, loopback, `10.90.90.x`, or APIPA). Por…

---

### phase1_stay_on_ollama

**Query:** Did we stay on Ollama or switch the agent to PowerInfer?

**Intent:** Phase 1 closed: stay on Qwen/gpt-oss via Ollama. No PowerInfer route, no TinyChatEngine intake now.

**Gold ids:** `CHANGELOG/2026-09-02j_rag_embedding_scorer_and_phase1_close.md:0`

**Ranks (raw scorer):** lexical=1  hybrid=9  search_docs gold: L=True H=False  **lexical_keeps_gold_hybrid_drops**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02j_rag_embedding_scorer_and_phase1_close.md:0` **GOLD**  
   match_by=lexical score=13.9437  
   # 2026-09-02 — Phase 1 milestone closed; RAG Stages 1-2 implemented  
   # 2026-09-02 — Phase 1 milestone closed; RAG Stages 1-2 implemented ## Scope Two things happened in one turn, in this order: (1) operator explicitly overrode the Phase 1 gate for the RAG upgrade item specifically, then in the same reply gave the actual engine decision that closes Phase 1 ("continue to use the models we already have — Qwen models, gpt-oss"); (2) `EmbeddingScorer`/`HybridScorer` (RAG_EVALUATION.md Sta…

2. `CHANGELOG/2026-08-29_powerinfer_native_pipeline.md:0`  
   match_by=lexical score=13.2692  
   # 2026-08-29 — Native Windows PowerInfer conversion pipeline  
   # 2026-08-29 — Native Windows PowerInfer conversion pipeline ## What changed - Added `tools/powerinfer/`: parameterized runner for `prosparse-7b` (supported sparse PoC) and `llama31-8b-abliterated-relu` (research route, `f=14336`, `--vocabtype bpe`). Same dump/train/convert/quantize/package/bench scripts. - Orchestrator is `tools/powerinfer/run_pipeline.ps1`. GPU, download, and CMake stages require `-Execute`. Defau…

3. `CHANGELOG/2026-08-29_powerinfer_control_plane.md:0`  
   match_by=lexical score=11.4758  
   # 2026-08-29 — PowerInfer control-plane evaluation scaffold  
   # 2026-08-29 — PowerInfer control-plane evaluation scaffold ## What changed - Added `local_agent/powerinfer_openai_proxy.py`: a dependency-free, loopback-only OpenAI-style `/v1/chat/completions` and `/v1/models` adapter for a separately running local PowerInfer `server` process. It translates text-only Llama-2-family chat messages to PowerInfer `/completion`, supports normal and SSE replies, bounds requests, and ref…

4. `CHANGELOG/2026-09-03r_mac_persistence_reboot.md:0`  
   match_by=lexical score=11.1929  
   # 2026-09-03r — Louises-MBP persistence reboot (WG-off, tunnel-auto, ollama-auto)  
   # 2026-09-03r — Louises-MBP persistence reboot (WG-off, tunnel-auto, ollama-auto) Live reboot verification of Louises-MBP on the afternoon of 2026-09-03 ET. Did **not** sudo. Did **not** `launchctl kickstart` ollama, celery, or WireGuard. Did **not** launch WireGuard.app. Did **not** run `wg-quick` by hand. Letter `q` was already taken (`2026-09-03q_ethernet_profile_private_dashboard.md`). `scripts/next_changelog_id…

5. `CHANGELOG/2026-09-02y_first_bot_watch_status_sync.md:0`  
   match_by=lexical score=10.8549  
   (no heading)  
   ﻿# 2026-09-02y — first bot 6pm watch: GROK_STATUS inspect-sync only ## Scope Inspect-only Keep-projects-moving run at ~6:10 PM ET 2026-09-02. **INSPECT-SYNC ONLY** — no tests, no GPU, no downloads, no Harmontown reopen, no PowerInfer execute. Did not edit `local_agent/` code. Read-only `farm_health --json` and `/api/status`. ## Why `GROK_STATUS.md` Current still stopped at the ~10:25 AM ET morning sync (r76 / overni…

**Hybrid search_docs**

1. `CHANGELOG/2026-08-29_powerinfer_control_plane.md:0`  
   match_by=both score=0.0315  
   # 2026-08-29 — PowerInfer control-plane evaluation scaffold  
   # 2026-08-29 — PowerInfer control-plane evaluation scaffold ## What changed - Added `local_agent/powerinfer_openai_proxy.py`: a dependency-free, loopback-only OpenAI-style `/v1/chat/completions` and `/v1/models` adapter for a separately running local PowerInfer `server` process. It translates text-only Llama-2-family chat messages to PowerInfer `/completion`, supports normal and SSE replies, bounds requests, and ref…

2. `CHANGELOG/2026-08-29_powerinfer_native_pipeline.md:0`  
   match_by=both score=0.0291  
   # 2026-08-29 — Native Windows PowerInfer conversion pipeline  
   # 2026-08-29 — Native Windows PowerInfer conversion pipeline ## What changed - Added `tools/powerinfer/`: parameterized runner for `prosparse-7b` (supported sparse PoC) and `llama31-8b-abliterated-relu` (research route, `f=14336`, `--vocabtype bpe`). Same dump/train/convert/quantize/package/bench scripts. - Orchestrator is `tools/powerinfer/run_pipeline.ps1`. GPU, download, and CMake stages require `-Execute`. Defau…

3. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-26.md:3`  
   match_by=both score=0.0286  
   ### 2026-08-30 — PowerInfer next-candidate research  
   annot touch Equal Shares evidence. Both render paths preserve all preflights, the global GPU Block control, and the append-only remote audit. The currently running desktop process may still be the previous loaded code. Apply these UI/server changes by restarting only the local-agent launcher at a time when no response is actively streaming. Do not restart ComfyUI. ## Remaining work that requires an operator decision…

4. `CHANGELOG/2026-08-29k_powerinfer_chat_picker.md:0`  
   match_by=both score=0.0276  
   # 2026-08-29 — PowerInfer as a normal local-agent chat-picker backend  
   # 2026-08-29 — PowerInfer as a normal local-agent chat-picker backend ## What changed - Design: `docs/POWERINFER_CHAT_PICKER_DESIGN_2026-08-29.md`. The router is still an Ollama CPU/GPU handoff, not a multi-engine registry. PowerInfer joins the picker the same way `gpt-oss-20b-heretic` does: always visible, GPU-only, never an automatic default, never a silent Huihui/CPU substitute. - `local_agent/router.py` - `chat_…

5. `CHANGELOG/2026-08-29f_powerinfer_fatrelu_operator_decision.md:0`  
   match_by=both score=0.0273  
   # 2026-08-29 — PowerInfer FATReLU operator decision note (prosparse-7b parked)  
   # 2026-08-29 — PowerInfer FATReLU operator decision note (prosparse-7b parked) ## What changed - Added `docs/POWERINFER_FATRELU_OPERATOR_DECISION_2026-08-29.md`. It records that the already-ingested `SparseLLM/prosparse-llama-2-7b` checkpoint is FATReLU / `SparseLlamaForCausalLM`, that PowerInfer's relu-gate rejects it, and that the operator must choose (a) a supported ReLU/ReLU² sparse model, (b) wait for upstream …

---

### empty_search_means_unsupported

**Query:** If search_docs returns nothing, may the agent answer from training anyway?

**Intent:** Empty fused pool means local docs do not establish the claim. MIN_EMBED_SIMILARITY=0.35 exists so RRF cannot return 'closest anyway'.

**Gold ids:** `CHANGELOG/2026-09-02j_rag_embedding_scorer_and_phase1_close.md:1`

**Ranks (raw scorer):** lexical=25  hybrid=43  search_docs gold: L=False H=False  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`  
   match_by=lexical score=16.1205  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

2. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=lexical score=15.3369  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

3. `local_agent/UPGRADE/03_memory_and_polish.md:1`  
   match_by=lexical score=14.037  
   ## Job 3 — harden web search  
   an returning empty — a silently empty search is the kind of wrong-measurement failure this project has been bitten by repeatedly - add a `search_docs`-first note in the tool description: local docs before the web, for anything about this project Also make `fetch_url` handle redirects, non-HTML content types, and large pages without dumping binary into the context. ## Job 4 — the code execution question ChatGPT Deskt…

4. `CHANGELOG/2026-08-23_retrieval_over_tree.md:0`  
   match_by=lexical score=13.8308  
   # 2026-08-23 — UPGRADE 02 (retrieval half): BM25 search over the document tree  
   # 2026-08-23 — UPGRADE 02 (retrieval half): BM25 search over the document tree ## What changed ### local_agent/retrieval.py (new) - stdlib-only BM25 retrieval. No rank_bm25, no sklearn, no downloads. - `LexicalScorer` — 35-line BM25 (K1=1.5, b=0.75). Swappable via `ScorerProtocol`. - `EmbeddingScorer` — stub placeholder for UPGRADE 05's embedding model. - Indexes 77 files across `docs/**/*.md`, `CLAUDE.md`, `README.…

5. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:0`  
   match_by=lexical score=13.5468  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal)  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal) 18 real questions this project has actually needed answered, each with ground-truth chunk ids read from the live index. Re-runnable against any future scorer. This is the Stage 5 set that 2026-09-02ab left as an operator lever, and the measurement 2026-09-03ae said FlashRank needed before a default-path change. ## Fixture `local_agent/evaluations…

**Hybrid search_docs**

1. `local_agent/UPGRADE/02_context_and_retrieval.md:1`  
   match_by=both score=0.0311  
   ## Job 2 — expose it as a tool  
   heading** so the agent can cite where a claim came from — a claim without a source is not evidence in this project. It is a read-only tool; it never writes. Update `CONVERSATION_RULES` in `agent.py`: for any question about a rule, a decision, why something is the way it is, or project history — **search the docs first**; `read_doc` stays for reading a whole named file. ## Job 3 — shrink the compiled brief Now that r…

2. `local_agent/UPGRADE/03_memory_and_polish.md:1`  
   match_by=both score=0.0308  
   ## Job 3 — harden web search  
   an returning empty — a silently empty search is the kind of wrong-measurement failure this project has been bitten by repeatedly - add a `search_docs`-first note in the tool description: local docs before the web, for anything about this project Also make `fetch_url` handle redirects, non-HTML content types, and large pages without dumping binary into the context. ## Job 4 — the code execution question ChatGPT Deskt…

3. `CHANGELOG/2026-09-02l_rag_stage4_agentic_self_correction.md:0`  
   match_by=both score=0.0307  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs  
   # 2026-09-02 — RAG Stage 4: agentic self-correction loop over local docs ## Scope Continuing the RAG upgrade (RAG_EVALUATION.md) after Phase 1 closed and Stages 1-2 were verified. This is Stage 4 — the piece that actually addresses the originally-flagged "biggest weakness" (no retry/self-correction when a local-docs search comes back empty or off-target). Stages 1-2 only improved the retriever; this adds judgment an…

4. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.0298  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

5. `local_agent/UPGRADE/DEEP_RESEARCH_grok_prompt.md:0`  
   match_by=both score=0.0289  
   # Grok agent prompt — add a `deep_research` tool with a pluggable search backend  
   # Grok agent prompt — add a `deep_research` tool with a pluggable search backend Paste into Grok (or any coding agent). Work in the repo `COMFYUI_STORY_HANDOFF_2026-08-09/`, in `local_agent/`. Read `local_agent/tools.py` (especially `web_search`, `fetch_url`, the `_TOOLS` registry and `_SCHEMAS`), `local_agent/agent.py`, `local_agent/router.py`, and `local_agent/README.md` before writing anything. **Constraints:** P…

---

### duration_ladder_not_seed

**Query:** Speech came back slurred — should I reroll the seed or change the duration?

**Intent:** Gibberish/mispronunciation → duration ladder, seed held fixed. Seed is the wrong-voice knob only.

**Gold ids:** `docs/H3_PROMPT_RULES.md:8`, `CHANGELOG/2026-08-18_duration_ladder.md:0`

**Ranks (raw scorer):** lexical=2  hybrid=1  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `docs/VOICE_CLONING_MODULE.md:2`  
   match_by=lexical score=18.6552  
   ## Render order  
   the one integration step left to you. `voice_sample_clips.json` holds the full spec for the twelve VOX clips — id, anchor, duration, frame count already rounded to 5 mod 17, seed, dialogue and a complete prompt following the house style. They are single-anchor by design; a closing frame would force the take to arrive at a pose, which fights thirteen seconds of talking. ## `voice_approval_gate.json` ```json { "schema…

2. `docs/H3_PROMPT_RULES.md:8` **GOLD**  
   match_by=lexical score=17.776  
   ## 10. The DURATION LADDER — how to retry gibberish and mispronounced words. Added 2026-08-18.  
   ." So from a base length **D**, rungs alternate outward, **up first**: ``` D D+1 D-1 D+2 D-2 D+3 D-3 D+4 D-4 ``` Implemented once, in `work/duration_ladder.py`. Nothing else may reimplement it. ``` python work\duration_ladder.py --seconds 10 # any base python work\duration_ladder.py --clip 00B # a story clip, capped at its script ``` ### Why duration and not the seed The number of words is fixed by the script. The s…

3. `CHANGELOG/2026-08-18_duration_ladder.md:0` **GOLD**  
   match_by=lexical score=17.5233  
   # 2026-08-18 — the duration ladder becomes the retry rule  
   # 2026-08-18 — the duration ladder becomes the retry rule ## What changed The retry knob for bad speech is now the **duration**, not the seed. Operator instruction, verbatim: > "when generating audio and trying to get perfect English words (getting rid of > gibberish or mispronounced words) use this generation pattern. Example start at > 10 sec; if gen is bad (has mispronounced words) add a second. If that does not …

4. `START_VOICE_AUDITIONS.md:1`  
   match_by=lexical score=16.6557  
   ## Job 1 — preflight, before the GPU  
   **One backend, ever.** The runner claims `runtime/render_queue_owner.json` itself; do not bypass it. ## Job 2 — render the 27 auditions ``` python work\render_voice_auditions.py ``` Roughly 2–3 hours. One clean backend per render, thermal guard before and after. Output lands in `story/AUDITION_<slug>/`, progress in `outputs/equal_shares/voice_audition_manifest.json`. ### The three things that make an audition valid …

5. `CHANGELOG/2026-08-17b_pace_correction_and_auditions.md:0`  
   match_by=lexical score=16.3582  
   # 2026-08-17 (later) — pace corrected from the golden set, and a correction to my own doctrine  
   # 2026-08-17 (later) — pace corrected from the golden set, and a correction to my own doctrine ## What changed - `work/build_audio_pass_durations.py`: `WORDS_PER_SEC` **3.5 -> 2.5**, `TAIL_MARGIN` 1.2 -> 1.5. Durations regenerated; omni config resynced. - **New** `work/build_voice_auditions.py` and 17 audition packs on the Desktop at `EQUAL_SHARES_VOICE_AUDITIONS\`. ## Why — and a doctrine I got wrong Measured the s…

**Hybrid search_docs**

1. `CHANGELOG/2026-08-18_duration_ladder.md:0` **GOLD**  
   match_by=both score=0.0323  
   # 2026-08-18 — the duration ladder becomes the retry rule  
   # 2026-08-18 — the duration ladder becomes the retry rule ## What changed The retry knob for bad speech is now the **duration**, not the seed. Operator instruction, verbatim: > "when generating audio and trying to get perfect English words (getting rid of > gibberish or mispronounced words) use this generation pattern. Example start at > 10 sec; if gen is bad (has mispronounced words) add a second. If that does not …

2. `docs/H3_PROMPT_RULES.md:8` **GOLD**  
   match_by=both score=0.0323  
   ## 10. The DURATION LADDER — how to retry gibberish and mispronounced words. Added 2026-08-18.  
   ." So from a base length **D**, rungs alternate outward, **up first**: ``` D D+1 D-1 D+2 D-2 D+3 D-3 D+4 D-4 ``` Implemented once, in `work/duration_ladder.py`. Nothing else may reimplement it. ``` python work\duration_ladder.py --seconds 10 # any base python work\duration_ladder.py --clip 00B # a story clip, capped at its script ``` ### Why duration and not the seed The number of words is fixed by the script. The s…

3. `CHANGELOG/2026-08-17b_pace_correction_and_auditions.md:0`  
   match_by=both score=0.0313  
   # 2026-08-17 (later) — pace corrected from the golden set, and a correction to my own doctrine  
   # 2026-08-17 (later) — pace corrected from the golden set, and a correction to my own doctrine ## What changed - `work/build_audio_pass_durations.py`: `WORDS_PER_SEC` **3.5 -> 2.5**, `TAIL_MARGIN` 1.2 -> 1.5. Durations regenerated; omni config resynced. - **New** `work/build_voice_auditions.py` and 17 audition packs on the Desktop at `EQUAL_SHARES_VOICE_AUDITIONS\`. ## Why — and a doctrine I got wrong Measured the s…

4. `START_LOCAL_AGENT.md:4`  
   match_by=both score=0.0305  
   ## Job 2 — replace the **2** remaining provisional voice masters  
   shares/voices/<slug>/`, never overwriting, then re-run `sync_omni_audio_config.py`. Start with `048_Terminal_voice` — 12 s of solo scripted speech. ## Job 3 — the soundtrack pass All 124 clips at **0.2 MP**, ref2va, non-Turbo, 20 steps, `res_multistep` / `simple`, denoise 1.0, 24 fps, 8-bit, one clean backend per clip, **using the shortened `frames` from the config**. ### Why the length matters more than anything el…

5. `docs/GOLDEN_REFERENCE/PROVEN_FACTS.md:2`  
   match_by=both score=0.0292  
   ### The consequences, which are easy to get wrong  
   till required** and cannot be skipped by harvesting this folder. *(Corrected 2026-08-18: this section originally said 14 speaking takes and listed `17.mp4` as having no dialogue. The harvest tool read prompts only from `PrimitiveStringMultiline` nodes and `17.mp4` carries its prompt inline on the sampler node, so its two spoken lines were invisible. Tool fixed.)* --- ## 3. Silence does not cause gibberish The claim …

---

### compaction_prefetch_threshold

**Query:** At what context fill fraction does compaction prefetch start?

**Intent:** PROACTIVE_THRESHOLD = 0.80 of num_ctx, not at overflow.

**Gold ids:** `CHANGELOG/2026-09-02u_compaction_prefetch.md:2`, `docs/ARCHITECTURE.md:2`

**Ranks (raw scorer):** lexical=10  hybrid=8  search_docs gold: L=False H=False  **different_no_gold_or_partial**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02u_compaction_prefetch.md:4`  
   match_by=lexical score=21.6052  
   ## Files modified  
   ) elif (not lightweight_turn and prompt_tokens > compaction_prefetch.PROACTIVE_THRESHOLD * num_ctx): _prefetch_sl = _summarizable_slice(msgs) if (len(_prefetch_sl) >= 2 and sum(len(str(_m.get("content", ""))) for _m in _prefetch_sl) >= 600): compaction_prefetch.maybe_start(_prefetch_sl) ``` ## What this does not do - Does not cancel or replace an in-flight background job when a new slice is seen (ignore-if-busy — th…

2. `CHANGELOG/2026-09-03af_compaction_prefetch_live_verify.md:0`  
   match_by=lexical score=18.7584  
   # 2026-09-03af — compaction_prefetch live-verified past 0.80; ignore-if-busy made atomic  
   # 2026-09-03af — compaction_prefetch live-verified past 0.80; ignore-if-busy made atomic ## What this session did `compaction_prefetch.py` had 30 unit tests and no hop-loop / `agent.answer()` drive past `PROACTIVE_THRESHOLD = 0.80`. This session ran the real trim/prefetch fork (and a mocked `agent.answer()` long conversation) through that band, then overflow. ## What held - **Threshold.** The hop-loop fires `maybe_s…

3. `CHANGELOG/2026-09-02u_compaction_prefetch.md:3`  
   match_by=lexical score=18.4701  
   ## Files created  
   empty for tiny list, consistent fingerprint with compaction_prefetch - `TestTrimContextIntegration` (5): prefetch used when ready (scenario 1), synchronous farm called when no prefetch (scenario 2), local fallback when all farm paths return None (scenario 5), emit note includes farm model name, slice-expanded discard falls through to synchronous path (scenario 4) ## Files modified **`local_agent/agent.py`** 1. Impor…

4. `docs/ARCHITECTURE.md:1`  
   match_by=lexical score=18.4439  
   ## 2. End-to-end flow  
   o 25–30s helper timeout. `should_route(kind, blocking=)` is the classifier: | kind | blocking | farm-eligible when reachable? | |---|---|---| | summarize | True (overflow / operator turn) | **never** — warm ~18.5s, cold ~55s vs local 12s | | summarize | False (prefetch) | yes | | embed | True (`search_docs` stale chunks) | yes — warm ~0.58s | | anything else | — | no | ### Compaction (in `agent.answer()` hop loop) E…

5. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:0`  
   match_by=lexical score=17.6931  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal)  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal) 18 real questions this project has actually needed answered, each with ground-truth chunk ids read from the live index. Re-runnable against any future scorer. This is the Stage 5 set that 2026-09-02ab left as an operator lever, and the measurement 2026-09-03ae said FlashRank needed before a default-path change. ## Fixture `local_agent/evaluations…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02u_compaction_prefetch.md:4`  
   match_by=both score=0.0328  
   ## Files modified  
   ) elif (not lightweight_turn and prompt_tokens > compaction_prefetch.PROACTIVE_THRESHOLD * num_ctx): _prefetch_sl = _summarizable_slice(msgs) if (len(_prefetch_sl) >= 2 and sum(len(str(_m.get("content", ""))) for _m in _prefetch_sl) >= 600): compaction_prefetch.maybe_start(_prefetch_sl) ``` ## What this does not do - Does not cancel or replace an in-flight background job when a new slice is seen (ignore-if-busy — th…

2. `CHANGELOG/2026-09-03af_compaction_prefetch_live_verify.md:0`  
   match_by=both score=0.032  
   # 2026-09-03af — compaction_prefetch live-verified past 0.80; ignore-if-busy made atomic  
   # 2026-09-03af — compaction_prefetch live-verified past 0.80; ignore-if-busy made atomic ## What this session did `compaction_prefetch.py` had 30 unit tests and no hop-loop / `agent.answer()` drive past `PROACTIVE_THRESHOLD = 0.80`. This session ran the real trim/prefetch fork (and a mocked `agent.answer()` long conversation) through that band, then overflow. ## What held - **Threshold.** The hop-loop fires `maybe_s…

3. `CHANGELOG/2026-09-02u_compaction_prefetch.md:3`  
   match_by=both score=0.0313  
   ## Files created  
   empty for tiny list, consistent fingerprint with compaction_prefetch - `TestTrimContextIntegration` (5): prefetch used when ready (scenario 1), synchronous farm called when no prefetch (scenario 2), local fallback when all farm paths return None (scenario 5), emit note includes farm model name, slice-expanded discard falls through to synchronous path (scenario 4) ## Files modified **`local_agent/agent.py`** 1. Impor…

4. `CHANGELOG/2026-09-02u_compaction_prefetch.md:0`  
   match_by=both score=0.0306  
   # 2026-09-02 — compaction_prefetch: proactive pre-compaction trigger  
   # 2026-09-02 — compaction_prefetch: proactive pre-compaction trigger ## Scope Closes the last open item in `TODO.md` Phase 2 item 5 ("Not built: agent.py-side decision logic that proactively pre-compacts context before the window fills"). Implements the background-trigger design reviewed and confirmed before implementation in this session. The existing synchronous path (`farm_offload.py` → `context_compactor`) is un…

5. `CHANGELOG/2026-09-03af_compaction_prefetch_live_verify.md:1`  
   match_by=both score=0.0306  
   ## Real gap found and fixed  
   l_agent/compaction_prefetch.py`: construct the `Thread` and publish it on `_state["thread"]` in the same critical section as the fingerprint reservation. `t.start()` stays outside the lock so a fast farm completion cannot deadlock on `_lock`. **Test that would have caught it:** `test_concurrent_different_fingerprints_start_only_one_farm_job`. 8 independent repeats, 8/8. ## Observed, not a correctness bug Growing use…

---

### gpu_idle_but_cpu_8b

**Query:** Why did GPU chat fall back to the CPU 8B when VRAM was almost empty?

**Intent:** GPU Ollama :11434 was down (Case B). VRAM 73 MB was below VRAM_BUSY_MB=2500; routing itself was correct.

**Gold ids:** `CHANGELOG/2026-08-25_gpu_routing_fix.md:0`

**Ranks (raw scorer):** lexical=10  hybrid=2  search_docs gold: L=False H=True  **hybrid_recovers_gold**

**Lexical search_docs**

1. `CHANGELOG/2026-08-30_gpu_only_pin_before_eviction.md:0`  
   match_by=lexical score=23.041  
   # 2026-08-30 — GPU-only pins must not become CPU when eviction is unverified  
   # 2026-08-30 — GPU-only pins must not become CPU when eviction is unverified ## What changed `local_agent/router.py` `decide()` ran the busy-GPU eviction-verification block (the early `Decision(tier="cpu", model=None, ... eviction could not be verified)`) **before** `is_powerinfer_model(model)` and `is_gpu_only_opt_in_model(model)`. Those later checks exist so a pinned Heretic or PowerInfer chat refuses with `tier="…

2. `CHANGELOG/2026-08-30_decide_early_return_audit.md:2`  
   match_by=lexical score=21.3801  
   ## The evidence — every `decide()` return, in execution order  
   s` not verified | `tier="cpu"`, `model=None`, "eviction could not be verified" | `test_unverified_gpu_eviction_refuses_cpu_handoff` (primary pin). The GPU-only gap here was the bug fixed today: `test_gpu_only_opt_in_pin_refuses_when_busy_even_if_eviction_unverified`, `test_powerinfer_pin_refuses_when_busy_even_if_eviction_unverified`, plus the original Heretic busy test. | | Unknown / unavailable pin | `model not in…

3. `CHANGELOG/2026-08-30_decide_early_return_audit.md:1`  
   match_by=lexical score=20.7064  
   ## What changed  
   _gpu_only_opt_in_model()` checks. No speculative restructure. ## Why Two GPU-only pins (Heretic and PowerInfer) were the same ordering bug: an earlier `Decision(tier="cpu")` short-circuited a later pin check that is supposed to win with `tier="gpu", model=None`. That is a pattern. Walking every return once is cheaper than finding the next instance during a feature add. ## The evidence — every `decide()` return, in e…

4. `docs/design_notes/architecture_audit_2026-08-27.md:5`  
   match_by=lexical score=18.4443  
   ## 2. Chroma DB memory persistence  
   e time. Nothing coordinates them the way `_WORKER_LOCK` coordinates thread startup. I have not reproduced a failure — this would need to be exercised under real concurrent load to confirm one way or the other — but it's the kind of gap worth closing before this subsystem sees more traffic, and it's cheap to close by fixing the client-caching issue above at the same time. ## 3. CPU/GPU dynamic resource routing **What…

5. `local_agent/UPGRADE/10_dynamic_model_fallback.md:2`  
   match_by=lexical score=17.7678  
   ## Step 3 — Strategy 2: reactive fallback (backstop)  
   nt ("14B unavailable/over VRAM — retrying on 8B"), `router.unload(GPU_HOST, GPU_PRIMARY_MODEL)` to free the card, then re-issue the same messages against `GPU_FALLBACK_MODEL` once. If the fallback also fails, surface a clean `error` — never a stack trace. - Only one downgrade step (14B → 8B), never a loop. If already on the 8B, do not retry the 8B against itself. ## Step 4 — model lifecycle (avoid VRAM contention be…

**Hybrid search_docs**

1. `local_agent/UPGRADE/10_dynamic_model_fallback.md:2`  
   match_by=both score=0.031  
   ## Step 3 — Strategy 2: reactive fallback (backstop)  
   nt ("14B unavailable/over VRAM — retrying on 8B"), `router.unload(GPU_HOST, GPU_PRIMARY_MODEL)` to free the card, then re-issue the same messages against `GPU_FALLBACK_MODEL` once. If the fallback also fails, surface a clean `error` — never a stack trace. - Only one downgrade step (14B → 8B), never a loop. If already on the 8B, do not retry the 8B against itself. ## Step 4 — model lifecycle (avoid VRAM contention be…

2. `CHANGELOG/2026-08-25_gpu_routing_fix.md:0` **GOLD**  
   match_by=both score=0.0307  
   # 2026-08-25 — GPU routing fix: GPU Ollama server down (Case B)  
   # 2026-08-25 — GPU routing fix: GPU Ollama server down (Case B) ## Diagnostic Four checks ran against the live agent to identify why chat was routing to CPU 8B instead of GPU 14B. Results: ``` === PORT 8188 === listening: False ← not ComfyUI === GPU MEMORY === used_mb: 73 ← well below VRAM_BUSY_MB=2500 free_mb: 15905 compute_procs: [brave.exe, brave.exe, llama-server.exe] ← all browser/Ollama === GPU OLLAMA SERVER :…

3. `CHANGELOG/2026-08-30_gpu_only_pin_before_eviction.md:0`  
   match_by=both score=0.0294  
   # 2026-08-30 — GPU-only pins must not become CPU when eviction is unverified  
   # 2026-08-30 — GPU-only pins must not become CPU when eviction is unverified ## What changed `local_agent/router.py` `decide()` ran the busy-GPU eviction-verification block (the early `Decision(tier="cpu", model=None, ... eviction could not be verified)`) **before** `is_powerinfer_model(model)` and `is_gpu_only_opt_in_model(model)`. Those later checks exist so a pinned Heretic or PowerInfer chat refuses with `tier="…

4. `local_agent/UPGRADE/12_resource_and_safety_hardening.md:1`  
   match_by=both score=0.0284  
   ## Job 1 — explicit `keep_alive` so models release VRAM promptly  
   n every message — do not set interactive chat to `0`. - Where a queued job finishes and nothing else is pending, the watcher still explicitly `router.unload()`s (existing behaviour) — belt and suspenders. Test (mock the HTTP post): a watcher/queue request carries the short `keep_alive`; an interactive chat request carries the modest one; the value reaches the payload. ## Job 2 — quantized KV cache to reclaim VRAM at…

5. `CHANGELOG/2026-08-30_decide_early_return_audit.md:1`  
   match_by=both score=0.0282  
   ## What changed  
   _gpu_only_opt_in_model()` checks. No speculative restructure. ## Why Two GPU-only pins (Heretic and PowerInfer) were the same ordering bug: an earlier `Decision(tier="cpu")` short-circuited a later pin check that is supposed to win with `tier="gpu", model=None`. That is a pattern. Walking every return once is cheaper than finding the next instance during a feature add. ## The evidence — every `decide()` return, in e…

---

### judge_not_registered

**Query:** Why did the first judge_transcript batch fail as NotRegistered?

**Intent:** Mac worker_farm code predated 2026-09-02c; old tasks.py had no judge_transcript.

**Gold ids:** `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md:1`

**Ranks (raw scorer):** lexical=2  hybrid=12  search_docs gold: L=True H=False  **lexical_keeps_gold_hybrid_drops**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md:0`  
   match_by=lexical score=20.1944  
   # 2026-09-02d — judge_evaluation: first live end-to-end run verified on Mac worker  
   # 2026-09-02d — judge_evaluation: first live end-to-end run verified on Mac worker ## What this session completed Session 2026-09-02c built and unit-tested the judge_evaluation workflow but left four things open: grant the `judge` queue to mac_worker, confirm the Mac runs a real judge task, verify the ACL DENY behaviour, and write the CHANGELOG. This session closes all four. --- ## Infrastructure state at start - Ph…

2. `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md:1` **GOLD**  
   match_by=lexical score=20.1508  
   ## Step 2 — First submission attempt and root cause of NotRegistered  
   - Submitted `--limit 3` after granting the queue - All 3 failed: `celery.exceptions.NotRegistered: 'local_agent.worker_farm.tasks.judge_transcript'` - Root cause: Mac's worker_farm code predated the 2026-09-02c session. The old `tasks.py` had no `judge_transcript`, so the worker received the task, could not find it registered, and returned FAILURE immediately. --- ## Step 3 — Mac worker environment rebuilt SSH was n…

3. `CHANGELOG/2026-09-03d_farm_judge_live_test_and_status_outage_alert.md:0`  
   match_by=lexical score=17.7901  
   # 2026-09-03d — live judge integration test and farm-status outage alert  
   # 2026-09-03d — live judge integration test and farm-status outage alert ## What Two worker-farm changes, both inside `local_agent/worker_farm/` (plus this changelog): 1. Live integration tests now submit a real `judge_transcript` task, matching the existing summarize/embed pattern. 2. `farm_status_daemon` logs a greppable `FARM_STATUS_OUTAGE` line after N consecutive failed health checks. Not wired into `agent.py` …

4. `CHANGELOG/2026-09-02d_first_bot_watch_status_sync.md:0`  
   match_by=lexical score=16.9307  
   # 2026-09-02d — first bot morning watch: GROK_STATUS inspect-sync only  
   # 2026-09-02d — first bot morning watch: GROK_STATUS inspect-sync only ## Scope Inspect-only Keep-projects-moving run at ~10:25 AM ET 2026-09-02. **INSPECT-SYNC ONLY** — no tests, no GPU, no downloads, no Harmontown reopen, no PowerInfer execute. Did not edit code under `local_agent/` beyond reading `APP_REVISION` in `server.py`. ## Why `GROK_STATUS.md` Current still claimed live `APP_REVISION` `2026-09-01-resident-…

5. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:0`  
   match_by=lexical score=16.3792  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal)  
   # 2026-09-03aj — Hand-judged retrieval eval fixture (FlashRank signal) 18 real questions this project has actually needed answered, each with ground-truth chunk ids read from the live index. Re-runnable against any future scorer. This is the Stage 5 set that 2026-09-02ab left as an operator lever, and the measurement 2026-09-03ae said FlashRank needed before a default-path change. ## Fixture `local_agent/evaluations…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02d_judge_evaluation_end_to_end_verified.md:0`  
   match_by=both score=0.0325  
   # 2026-09-02d — judge_evaluation: first live end-to-end run verified on Mac worker  
   # 2026-09-02d — judge_evaluation: first live end-to-end run verified on Mac worker ## What this session completed Session 2026-09-02c built and unit-tested the judge_evaluation workflow but left four things open: grant the `judge` queue to mac_worker, confirm the Mac runs a real judge task, verify the ACL DENY behaviour, and write the CHANGELOG. This session closes all four. --- ## Infrastructure state at start - Ph…

2. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-09-02.md:2`  
   match_by=both score=0.0313  
   ### Phase 1 (engine architecture evaluation) — closed  
   dency — correcting an assumption that it was a context/tool-orchestration harness (it's actually an autonomous ML-training-experiment loop). Two more plausible actual fits flagged instead: a template for a future Supervisor Loop, or for automating PowerInfer's own predictor/calibration tuning. Nothing cloned or run. (`CHANGELOG/2026-09-02g_autoresearch_resource_note.md`) ### judge_evaluation workflow — built, then v…

3. `CHANGELOG/2026-09-03d_farm_judge_live_test_and_status_outage_alert.md:0`  
   match_by=both score=0.0306  
   # 2026-09-03d — live judge integration test and farm-status outage alert  
   # 2026-09-03d — live judge integration test and farm-status outage alert ## What Two worker-farm changes, both inside `local_agent/worker_farm/` (plus this changelog): 1. Live integration tests now submit a real `judge_transcript` task, matching the existing summarize/embed pattern. 2. `farm_status_daemon` logs a greppable `FARM_STATUS_OUTAGE` line after N consecutive failed health checks. Not wired into `agent.py` …

4. `CHANGELOG/2026-09-02c_judge_evaluation_workflow.md:2`  
   match_by=both score=0.0286  
   ## What was built  
   changed since it was last queued (tracked in a small local ledger, `worker_farm/runtime/judge_ledger.json`), skips unchanged ones. Meant to be re-run repeatedly (cron/scheduled task) so the queue keeps refilling as real usage accumulates — the "always stay busy, scales with more machines" property the operator asked for, without inventing synthetic busywork. ## Verification ``` python -m py_compile local_agent/worke…

5. `CHANGELOG/2026-09-02c_judge_evaluation_workflow.md:0`  
   match_by=both score=0.0284  
   # 2026-09-02 — judge_evaluation: first real worker-farm workflow  
   # 2026-09-02 — judge_evaluation: first real worker-farm workflow ## Scope The operator's stated objective for the worker farm: make the local agent "better, more efficient, smarter, faster and more logical," keep workers continuously busy, and scale as more machines join — with the explicit requirement that the work actually helps the agent, not busywork. Of the four workflows in `docs/WORKER_FARM_ARCHITECTURE_PLAN_…

---

### farm_embed_no_celery_import

**Query:** How does the workstation send embed jobs to the farm without importing Celery?

**Intent:** farm_offload spawns worker_farm/.venv Python running _farm_submit_wait.py; returns None, never raises.

**Gold ids:** `CHANGELOG/2026-09-02s_farm_offload_routing.md:0`, `docs/ARCHITECTURE.md:1`

**Ranks (raw scorer):** lexical=6  hybrid=2  search_docs gold: L=False H=True  **hybrid_recovers_gold**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02o_summarize_embed_farm_queues.md:0`  
   match_by=lexical score=24.0772  
   # 2026-09-02 — worker farm: summarize/embed queue code (not yet live)  
   # 2026-09-02 — worker farm: summarize/embed queue code (not yet live) ## Scope Operator asked whether the worker farm is ready to start helping the local agent. Answer given: partially — transport is proven, but the specific task code didn't exist and the connected worker has no LLM installed. Operator chose to have the task code written now, deployment deferred. Implements `HARNESS_OPTIMIZATION.md` §4a. ## What was…

2. `docs/ARCHITECTURE.md:4`  
   match_by=lexical score=23.5291  
   ## 3. Modules  
   ()`. Never submits jobs. Live CLI is a diagnostic — the hot path does not import this module. Live 2026-09-02 worker name: `celery@Louises-MBP`. **`local_agent/worker_farm/farm_status_daemon.py`.** Interval writer (default 30s) of `worker_farm/farm_status.json` via `check_farm_health`. That snapshot **is** the hot-path reachability signal (`farm_offload.farm_reachable`). Related files (not the hot path): `celery_app…

3. `docs/RUNBOOK.md:1`  
   match_by=lexical score=19.0123  
   ## 0. Is this the workstation, or the farm?  
   (LAN IP tonight: `192.168.50.8`.) 3. From that Mac shell, ping/TCP the hub yourself (`10.90.90.1:6379`). 4. Only if LAN SSH also fails is the Mac actually down. Otherwise keep going — the farm process may be fine and the tunnel/path is the bug. Trap: the workstation's own connection flaking looks identical to "Redis is down" or "no workers" in `farm_health`. --- ## 1. Connectivity is not task availability `farm_heal…

4. `docs/ARCHITECTURE.md:3`  
   match_by=lexical score=18.8906  
   ### Local fallback  
   m stale"] remain["remaining chunks EmbeddingScorer._embed"] ollama["ollama_client.embed nomic-embed-text on CPU_HOST"] write["write knowledge/retrieval_embeddings.json"] score["score: query vector always local _embed"] vf --> lock --> routeE routeE -->|yes| farmE routeE -->|no| remain farmE --> remain --> ollama --> write score -.->|not farm| ollama ``` ## 3. Modules **`local_agent/agent.py`.** Imports `compaction_p…

5. `docs/FARM_HEALTH_RUNBOOK.md:0`  
   match_by=lexical score=18.7332  
   # Farm health runbook  
   # Farm health runbook Date: 2026-09-03. Diagnostic sequence from 2026-09-02 evening through ~2:55 AM ET. **Reboot persistence is not confirmed.** ## Trap Interface-up ≠ datapath. Windows hub and Mac `utun5` / `10.90.90.2` can both look Connected while Redis / SSH / ICMP over `10.90.90.0/28` are dead. Hot path: `farm_offload.farm_reachable()` reads `farm_status.json` with the same overall-healthy rule as the dashboar…

**Hybrid search_docs**

1. `docs/ARCHITECTURE.md:4`  
   match_by=both score=0.032  
   ## 3. Modules  
   ()`. Never submits jobs. Live CLI is a diagnostic — the hot path does not import this module. Live 2026-09-02 worker name: `celery@Louises-MBP`. **`local_agent/worker_farm/farm_status_daemon.py`.** Interval writer (default 30s) of `worker_farm/farm_status.json` via `check_farm_health`. That snapshot **is** the hot-path reachability signal (`farm_offload.farm_reachable`). Related files (not the hot path): `celery_app…

2. `CHANGELOG/2026-09-02s_farm_offload_routing.md:0` **GOLD**  
   match_by=both score=0.0311  
   # 2026-09-02 — farm_offload: workstation-side routing to summarize/embed queues  
   # 2026-09-02 — farm_offload: workstation-side routing to summarize/embed queues ## Scope Implements the "lightweight classifier" described in `HARNESS_OPTIMIZATION.md` §4a: "a decision point in `agent.py` (or a small new module it calls into) that chooses, for a given compaction or embedding need, whether to dispatch to the farm or fall back to the existing local/CPU path." Closes the last open item in `TODO.md` Pha…

3. `CHANGELOG/2026-09-02o_summarize_embed_farm_queues.md:0`  
   match_by=both score=0.0309  
   # 2026-09-02 — worker farm: summarize/embed queue code (not yet live)  
   # 2026-09-02 — worker farm: summarize/embed queue code (not yet live) ## Scope Operator asked whether the worker farm is ready to start helping the local agent. Answer given: partially — transport is proven, but the specific task code didn't exist and the connected worker has no LLM installed. Operator chose to have the task code written now, deployment deferred. Implements `HARNESS_OPTIMIZATION.md` §4a. ## What was…

4. `CHANGELOG/2026-08-29b_worker_farm_task_registration_fix.md:1`  
   match_by=both score=0.0292  
   ## Root cause  
   `RUN_PHASE1_SAMPLE.ps1` would appear to queue successfully, and the worker would silently discard every job with Celery's standard "Received unregistered task" behavior. Nothing in the existing 12-test suite caught this — all of it tests task-body logic directly (`tasks._run_distill(...)`) or patches `submit_distillation.app`, never the worker's actual app-loading path. ## Verification No live Redis was available in…

5. `docs/ARCHITECTURE.md:5`  
   match_by=both score=0.0291  
   ## 4. Queues  
   s; worker Ollama 120s. Warm Mac ~18.5s; cold ~55s. - **embed** — `embed_chunks`. `{id, text}` → `{id: vector}`, `nomic-embed-text:latest`, 768-dim. Producer: `EmbeddingScorer.vectors_for`. Caller 30s. Warm ~0.58s. Query embedding stays local. `distill` is declared and consumed only by the workstation Phase-1 worker, not the Mac. It is not part of the live Mac farm path. ## 5. Persistence and networking Star WireGuar…

---

### wireguard_icmp_not_health

**Query:** If ping to the WireGuard hub fails, is the farm down?

**Intent:** ICMP to 10.90.90.1 can fail on Windows firewall while TCP/SSH/Celery work. Do not treat ping as the health signal.

**Gold ids:** `docs/FARM_HEALTH_RUNBOOK.md:2`

**Ranks (raw scorer):** lexical=15  hybrid=10  search_docs gold: L=False H=False  **different_no_gold_or_partial**

**Lexical search_docs**

1. `docs/RUNBOOK.md:2`  
   match_by=lexical score=24.51  
   ## 1. Connectivity is not task availability  
   0.0.1:11434`) and live tests below. | Live (slow, not the fast suite): ``` local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v ``` Tonight ~6:42 PM: broker reachable, **no worker answered ping**, registered empty — Windows hub was up; Mac Celery was running on LAN but could not reach Redis over the tunnel. --- ## 2. Interface-up is not a datapath Windows hub …

2. `docs/RUNBOOK.md:1`  
   match_by=lexical score=23.8555  
   ## 0. Is this the workstation, or the farm?  
   (LAN IP tonight: `192.168.50.8`.) 3. From that Mac shell, ping/TCP the hub yourself (`10.90.90.1:6379`). 4. Only if LAN SSH also fails is the Mac actually down. Otherwise keep going — the farm process may be fine and the tunnel/path is the bug. Trap: the workstation's own connection flaking looks identical to "Redis is down" or "no workers" in `farm_health`. --- ## 1. Connectivity is not task availability `farm_heal…

3. `CHANGELOG/2026-09-02t_farm_health.md:0`  
   match_by=lexical score=22.64  
   # 2026-09-02t — standalone farm_health diagnostic  
   # 2026-09-02t — standalone farm_health diagnostic ## What Added `local_agent/worker_farm/farm_health.py`: a CLI + `check_farm_health(timeout_s=5.0)` helper that reports broker reachable / workers responding / latency_ms without submitting any summarize, embed, judge, or distill job. ## How it checks 1. Loads `local_agent/worker_farm/.env` the same way `_farm_submit_wait._load_env_file` does (does not override alread…

4. `docs/FARM_HEALTH_RUNBOOK.md:1`  
   match_by=lexical score=22.1405  
   ## 1. Health check (workstation, farm venv, repo root)  
   responding: no latency_ms: 1479.6 error: broker reachable, no worker answered ping registered-task status: no_workers workers: (none) registered: (none) missing_expected: ...connectivity_probe, ...judge_transcript, ...summarize_conversation, ...embed_chunks ``` Windows hub was up. Cached `farm_status.json` last healthy 4:45:56 PM ET — do not trust a stale snapshot. ## 2. Registered-task check (same CLI, added tonigh…

5. `docs/RUNBOOK.md:0`  
   match_by=lexical score=20.1481  
   # Worker-farm troubleshooting runbook  
   # Worker-farm troubleshooting runbook Date: 2026-09-03. Operator checklist from the 2026-09-02 evening through ~2:55 AM ET debug. **Docs-only.** This does not change farm code, plists, or LaunchAgents. Use this when the farm "looks broken": missing workers, green health that still fails jobs, a tunnel that says Connected but Redis/SSH are dead, or a daemon that exits with nothing useful in the terminal. Tonight's fu…

**Hybrid search_docs**

1. `docs/RUNBOOK.md:1`  
   match_by=both score=0.0325  
   ## 0. Is this the workstation, or the farm?  
   (LAN IP tonight: `192.168.50.8`.) 3. From that Mac shell, ping/TCP the hub yourself (`10.90.90.1:6379`). 4. Only if LAN SSH also fails is the Mac actually down. Otherwise keep going — the farm process may be fine and the tunnel/path is the bug. Trap: the workstation's own connection flaking looks identical to "Redis is down" or "no workers" in `farm_health`. --- ## 1. Connectivity is not task availability `farm_heal…

2. `docs/RUNBOOK.md:2`  
   match_by=both score=0.032  
   ## 1. Connectivity is not task availability  
   0.0.1:11434`) and live tests below. | Live (slow, not the fast suite): ``` local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_farm_integration -v ``` Tonight ~6:42 PM: broker reachable, **no worker answered ping**, registered empty — Windows hub was up; Mac Celery was running on LAN but could not reach Redis over the tunnel. --- ## 2. Interface-up is not a datapath Windows hub …

3. `docs/RUNBOOK.md:0`  
   match_by=both score=0.0315  
   # Worker-farm troubleshooting runbook  
   # Worker-farm troubleshooting runbook Date: 2026-09-03. Operator checklist from the 2026-09-02 evening through ~2:55 AM ET debug. **Docs-only.** This does not change farm code, plists, or LaunchAgents. Use this when the farm "looks broken": missing workers, green health that still fails jobs, a tunnel that says Connected but Redis/SSH are dead, or a daemon that exits with nothing useful in the terminal. Tonight's fu…

4. `CHANGELOG/2026-09-01i_wireguard_hub_standup.md:0`  
   match_by=both score=0.031  
   # 2026-09-01i — WireGuard hub stood up, Mac joined as first peer  
   # 2026-09-01i — WireGuard hub stood up, Mac joined as first peer ## What happened Continuation of the multi-node worker-farm setup described in `docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md` and the scripts written in `CHANGELOG/2026-09-01h_wireguard_hub_scripts.md`. All steps executed in one session; nothing was pre-staged. ## Steps completed ### WireGuard installation - Installed WireGuard 1.1 via `winget in…

5. `CHANGELOG/2026-09-02t_farm_health.md:0`  
   match_by=both score=0.0306  
   # 2026-09-02t — standalone farm_health diagnostic  
   # 2026-09-02t — standalone farm_health diagnostic ## What Added `local_agent/worker_farm/farm_health.py`: a CLI + `check_farm_health(timeout_s=5.0)` helper that reports broker reachable / workers responding / latency_ms without submitting any summarize, embed, judge, or distill job. ## How it checks 1. Loads `local_agent/worker_farm/.env` the same way `_farm_submit_wait._load_env_file` does (does not override alread…

---

### relullama_not_promotable

**Query:** Is ReluLLaMA eligible for the production model picker?

**Intent:** Failed 9/10 instruction-format cases; diagnostic-only, not registry/picker/routing.

**Gold ids:** `CHANGELOG/2026-09-02e_phase1_engine_evaluation_progress.md:0`, `CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md:5`

**Ranks (raw scorer):** lexical=16  hybrid=3  search_docs gold: L=False H=True  **hybrid_recovers_gold**

**Lexical search_docs**

1. `CHANGELOG/2026-08-30_turbosparse_status_audit.md:0`  
   match_by=lexical score=17.1995  
   # 2026-08-30 — TurboSparse parked-status documentation audit  
   # 2026-08-30 — TurboSparse parked-status documentation audit ## What was inspected (read-only except the doc edits below) - `CLAUDE.md` — Equal Shares safety + 2026-08-30 scope notice. No TurboSparse section. Not a contradiction: current work is deferred to `local_agent/README.md`, `TODO.md`, and `CHANGELOG/`. Left unchanged. - `local_agent/README.md` — PowerInfer picker said “predictor calibration is still in progr…

2. `CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md:4`  
   match_by=lexical score=12.9933  
   ## Quality-review packet prepared (no inference)  
   erifier applies explicit thresholds (default candidate mean >= 1.5 and no more than 0.25 below the baseline). This makes the separate human quality gate reproducible rather than a subjective one-off. - Prepared, unfilled packet: `validation/quality_review_packet.json` in the staged ReluLLaMA candidate. It is not evidence of quality and does not promote the model. ## Controlled baseline/candidate quality capture — ca…

3. `CHANGELOG/2026-08-30_readme_powerinfer_picker.md:0`  
   match_by=lexical score=11.085  
   # 2026-08-30 — README documents the PowerInfer picker contract  
   # 2026-08-30 — README documents the PowerInfer picker contract ## What changed `CHANGELOG/2026-08-30b_scope_reprioritization_doc_pass.md` left this open: > `local_agent/README.md` does not yet mention the PowerInfer chat-picker > integration … a real documentation gap Closed that gap. Documentation only. Did not touch `router.py`, `tools/powerinfer/`, or `work/`. | File | Change | |---|---| | `local_agent/README.md`…

4. `CHANGELOG/2026-08-30_powerinfer_batch_suite.md:0`  
   match_by=lexical score=10.5543  
   # 2026-08-30 — PowerInfer batch suite orchestrator  
   # 2026-08-30 — PowerInfer batch suite orchestrator ## What changed - Added `tools/powerinfer/batch_suite.ps1`: loops `models.json` ids / HF repos and calls existing `run_pipeline.ps1` stages (`show`, `intake`, `relu-gate`, `calib`, `dump`, `train`, `convert`, `quantize`, `package`). Default is plan-only; GPU/download/delete requires `-Execute`. - Default vault is `A:\PowerInferModels` (live vault as of 2026-08-30). …

5. `CHANGELOG/2026-08-30d_quality_review_responses_recorded.md:0`  
   match_by=lexical score=10.3319  
   # 2026-08-30 — ReluLLaMA quality packet: responses recorded, not reviewed  
   # 2026-08-30 — ReluLLaMA quality packet: responses recorded, not reviewed Operator-approved, bounded GPU comparison only. Did **not** score the rubric, did **not** write `router.py`, did **not** add the candidate to the picker, and did **not** call `tools/powerinfer/production_registry.py`. Status on the packet is `responses_recorded` (not `reviewed`). Reviewer name / `reviewed_at` left blank for Rhine. Packet: `A:\…

**Hybrid search_docs**

1. `CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md:4`  
   match_by=both score=0.0311  
   ## Quality-review packet prepared (no inference)  
   erifier applies explicit thresholds (default candidate mean >= 1.5 and no more than 0.25 below the baseline). This makes the separate human quality gate reproducible rather than a subjective one-off. - Prepared, unfilled packet: `validation/quality_review_packet.json` in the staged ReluLLaMA candidate. It is not evidence of quality and does not promote the model. ## Controlled baseline/candidate quality capture — ca…

2. `CHANGELOG/2026-08-30f_corrections.md:2`  
   match_by=both score=0.0303  
   ## What is NOT changed  
   are accurate evidence and must not be altered - `validation/acceptance_gate_20260830_175953.json` — throughput, FFN split, and VRAM results remain valid; the gate is a hardware/throughput gate and its conclusions are unaffected - Production registry — not touched - Picker pin — not set; the model is still not in the picker - Source HF files and read-only locks --- ## Remaining operator decisions (from `2026-08-30e`)…

3. `CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md:5` **GOLD**  
   match_by=both score=0.0288  
   ## Controlled baseline/candidate quality capture — candidate not promotable  
   lidation directory is read-only, so no evidence was overwritten. - Result: retain `relu-llama-7b` as an isolated candidate; it is not eligible for registry acceptance, proxy launch, model-picker exposure, or agent routing. Any future retry must first investigate Llama-2 prompt-template and instruction-tuning alignment, then repeat the same capture and human review. ## Resumed guarded continuation - The operator expl…

4. `CHANGELOG/2026-09-03aj_retrieval_hand_judged_eval.md:1`  
   match_by=both score=0.0267  
   ## HybridScorer result (this run)  
   table | ReluLLaMA in the model picker? | 17 | | empty_search_means_unsupported | empty search_docs → answer from training? | 19 | The other 13, including several paraphrases (`changelog letter`, `source citation`, `FlashRank default?`, `tinyengine on the 5080?`, duration vs seed), ranked 1–3. Evidence file: `local_agent/evaluations/retrieval_hand_judged_last_run.json`. ## What this does to the FlashRank decision 202…

5. `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md:3`  
   match_by=both score=0.0265  
   ## prosparse-7b retirement rationale  
   t unchanged. `PowerInfer/ReluLLaMA-7B` is the model the PowerInfer team actually built the pipeline and paper results around: LLaMA-2-7B retrained to use plain ReLU in place of SiLU, so every neuron is truly zero or positive with no floor. Its config.json is expected to show `hidden_act: "relu"` and `model_type: "llama"`, which the gate will accept without modification. ## What is needed from the operator Two free i…

---

### tinyengine_is_mcu

**Query:** Can the literal tinyengine package run on the RTX 5080?

**Intent:** mit-han-lab/tinyengine is microcontroller-only. The desktop sibling is TinyChatEngine; that was inferred, not stated.

**Gold ids:** `CHANGELOG/2026-09-02f_tinychatengine_intake_plan.md:0`

**Ranks (raw scorer):** lexical=2  hybrid=1  search_docs gold: L=True H=True  **both_have_gold_different_order**

**Lexical search_docs**

1. `CHANGELOG/2026-09-02e_phase1_engine_evaluation_progress.md:1`  
   match_by=lexical score=22.7063  
   ## Task 1 — PowerInfer: re-read in full, no new decision made  
   oad) but prompt/chat-template contract unresolved, blocking its own quality gate. No decision was made here — which route to invest further GPU/calibration effort in is recorded in `TODO.md` as an explicit operator decision (three options laid out: finish+approve the 32-pair TurboSparse set, resolve Bamboo-DPO's prompt contract, or drop PowerInfer and stay on Ollama). ## Task 2 — TinyEngine: researched, finding reco…

2. `CHANGELOG/2026-09-02f_tinychatengine_intake_plan.md:0` **GOLD**  
   match_by=lexical score=15.4335  
   # 2026-09-02 — TinyChatEngine research + staged intake plan  
   # 2026-09-02 — TinyChatEngine research + staged intake plan ## Scope Phase 1 / Task 2 (engine architecture evaluation) continuation. Operator asked to "research tinyengine and make a plan to try to implement it." Since the literal `mit-han-lab/tinyengine` project has no desktop/GPU path (microcontroller-only, confirmed in the prior research pass), this was read as referring to the sibling project `mit-han-lab/TinyCh…

3. `CHANGELOG/2026-08-24_attention_optimization_review.md:1`  
   match_by=lexical score=15.3328  
   ## Current live-test status  
   emains correctly blocked until that exact download is present. ## Next safe optimization The best candidate for the **agent**, not ComfyUI, is a controlled GPU-only Ollama test of Flash Attention plus q8_0 KV cache. This is deliberately not enabled in this change: it requires measured 14B VRAM/latency/quality and a clean yield-to-render check before it can be retained. ## Verification - Read-only inspection confirme…

4. `CHANGELOG/2026-08-29i_powerinfer_runbook_relullama.md:1`  
   match_by=lexical score=12.2645  
   ## The evidence  
   ` under `C:\PowerInferVault\relu-llama-7b\...`. Sections 2, 3, and 4 were left in place. ## What was verified after CPU-only string checks on the rewritten runbook (no GPU, no download, no `-Execute`): ```text relu-llama-7b ModelId commands: 12 prosparse-7b ModelId mentions: 3 (do-not-use / parked warnings only) D:\PowerInferModels: 0 C:\PowerInferVault: 8 FATReLU: 5 ## Section 2 / 3 / 4: present live stages all use…

5. `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md:3`  
   match_by=lexical score=12.0382  
   ## prosparse-7b retirement rationale  
   t unchanged. `PowerInfer/ReluLLaMA-7B` is the model the PowerInfer team actually built the pipeline and paper results around: LLaMA-2-7B retrained to use plain ReLU in place of SiLU, so every neuron is truly zero or positive with no floor. Its config.json is expected to show `hidden_act: "relu"` and `model_type: "llama"`, which the gate will accept without modification. ## What is needed from the operator Two free i…

**Hybrid search_docs**

1. `CHANGELOG/2026-09-02f_tinychatengine_intake_plan.md:0` **GOLD**  
   match_by=both score=0.0325  
   # 2026-09-02 — TinyChatEngine research + staged intake plan  
   # 2026-09-02 — TinyChatEngine research + staged intake plan ## Scope Phase 1 / Task 2 (engine architecture evaluation) continuation. Operator asked to "research tinyengine and make a plan to try to implement it." Since the literal `mit-han-lab/tinyengine` project has no desktop/GPU path (microcontroller-only, confirmed in the prior research pass), this was read as referring to the sibling project `mit-han-lab/TinyCh…

2. `CHANGELOG/2026-09-02e_phase1_engine_evaluation_progress.md:1`  
   match_by=both score=0.0323  
   ## Task 1 — PowerInfer: re-read in full, no new decision made  
   oad) but prompt/chat-template contract unresolved, blocking its own quality gate. No decision was made here — which route to invest further GPU/calibration effort in is recorded in `TODO.md` as an explicit operator decision (three options laid out: finish+approve the 32-pair TurboSparse set, resolve Bamboo-DPO's prompt contract, or drop PowerInfer and stay on Ollama). ## Task 2 — TinyEngine: researched, finding reco…

3. `CHANGELOG/2026-08-29i_powerinfer_prerequisite_audit.md:0`  
   match_by=both score=0.0292  
   # 2026-08-29 - PowerInfer native-build prerequisite audit  
   # 2026-08-29 - PowerInfer native-build prerequisite audit ## Read-only findings - `nvcc` is available: CUDA Toolkit 12.8, satisfying the RTX 5080 / `sm_120` minimum recorded by the native build plan. - NVIDIA reports an RTX 5080 with driver 595.97. - Visual Studio Community C++ build tools are present. - Visual Studio's bundled CMake executable exists, but CMake is not currently on the ordinary process PATH. - No `e…

4. `docs/design_notes/distributed_compute_assessment.md:0`  
   match_by=both score=0.0291  
   # Design note — distributed / offload compute assessment  
   # Design note — distributed / offload compute assessment _Authored 2026-08-24. Assessment of moving the agent LLM (and Whisper) off the RTX 5080 rig onto secondary machines so the 5080 stays dedicated to ComfyUI/diffusion. Verdict: worth doing for text; vision is the catch. No prompt written yet — operator paused it._ ## Verdict: yes, for the text/agent LLM - It turns VRAM contention from a software-arbitration prob…

5. `CHANGELOG/2026-08-29_powerinfer_setup_attempt.md:3`  
   match_by=both score=0.028  
   ## prosparse-7b retirement rationale  
   t unchanged. `PowerInfer/ReluLLaMA-7B` is the model the PowerInfer team actually built the pipeline and paper results around: LLaMA-2-7B retrained to use plain ReLU in place of SiLU, so every neuron is truly zero or positive with no floor. Its config.json is expected to show `hidden_act: "relu"` and `model_type: "llama"`, which the gate will accept without modification. ## What is needed from the operator Two free i…

---

