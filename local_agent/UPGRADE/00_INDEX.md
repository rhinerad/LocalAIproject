# Upgrade plan — getting the local agent closer to ChatGPT Desktop

## North star

This is a parity roadmap for a **local ChatGPT Desktop equivalent**. Equal Shares
is its first deep specialization, not the boundary of the product. General
assistant behavior and desktop UX take priority; project actions are added as
guarded tools without weakening evidence, render-queue or thermal protections.

Nine prompts. **Five need no internet at all**, one needs ~10 MB, one needs it
once, one needs a real connection. Run them in order; each is self-contained and pasteable into Claude
Code on its own.

| # | Prompt | Internet? | What it fixes |
|---|---|---|---|
| 1 | `01_native_tool_calling.md` | **no** | The hand-rolled `TOOL:` regex protocol → real function calling. **Biggest single win.** |
| 2 | `02_context_and_retrieval.md` | **no** | **BUILT 2026-08-23** (see `CHANGELOG/2026-08-23_retrieval_over_tree.md`). BM25 `search_docs` over 77 files (77 files, 306 chunks); brief trimmed 8.1 KB → 3.9 KB; `_trim_context` guard added. The num_ctx half was already delivered by the adaptive reasoning pair and was not re-done. |
| 3 | `03_memory_and_polish.md` | **no** | **BUILT 2026-08-22** (see `CHANGELOG/2026-08-22_upgrade3_memory_and_polish.md`). Memory across chats, the missing rename button, hardened web search, code-exec decision |
| 4 | `04_sensory_scaffolding.md` | **no** | Vision/audio/embedding tools built and wired **now**, no-op until the models exist |
| 5 | `05_models_after_internet.md` | **YES** | Swap to a smarter model, then switch the no-ops on |
| 6a | `06a_usb_direct.md` | ~10 MB | **Phone over a USB cable.** Proves the whole mobile client with zero network exposure. Do this first. |
| 6b | `06b_phone_app.md` | **no** | **Makes it a real phone app** — home screen icon, share sheet, camera, voice, phone files |
| 6 | `06_remote_access.md` | once | Then the same thing over cellular, via Tailscale |
| 7 | `07_batch_renderer.md` | **no** | **BUILT 2026-08-22** (`work/batch_render_folder.py`; see `CHANGELOG/2026-08-22_batch_renderer.md`). Point it at a folder of prompts + refs and it renders the batch. A general ComfyUI maker, separate from Equal Shares. |
| 8 | `08_gui_ctx_and_gpu_yield.md` | **no** | **BUILT 2026-08-23** (see `CHANGELOG/2026-08-23_gui_ctx_ceiling_and_yield.md`). GUI context ceiling select (Auto/8K/16K/24K/32K, localStorage, never raises adaptive) + Yield GPU button (`/api/yield_gpu`, evicts resident + preferred model). |
| 9 | `09_media_gpu_queue.md` | exact VLM already installed | **BUILT and superseded 2026-08-25.** Sensory analysis is pinned to the exact local Qwen2.5-VL Caption V4 Q4_K_M GGUF plus matched Q8_0 projector, started only by the background watcher when the GPU is free. There is no alternate VLM fallback; otherwise the file stays safely queued. See `CHANGELOG/2026-08-25_exact_qwen25_vl_caption_enforcement.md`. |
| 10 | `10_dynamic_model_fallback.md` | pull 8B+14B | Chat/reasoning tier picks **14B abliterated** for short context, **8B** past ~16K tokens (predictive), with a reactive OOM→8B retry. Installs `huihui_ai/qwen3-abliterated:14b` and `:8b`. |
| 11 | `11_android_sideband_agent.md` | Sideband fork | **Tier A BUILT and live-paired 2026-08-23. Tier B source overlay started 2026-08-25.** Stock Sideband already sends files/gallery images/mic audio through the paired bridge; the checked-in fork adds a direct camera attachment action. Android packaging, a custom agent conversation UI, and live phone acceptance remain separately gated. |
| 11-alt | `11_android_native_app.md` | research + SDK | Alternative to 11: a native app built from scratch over Reticulum. Kept for reference; prefer the Sideband path above unless a fork proves unworkable. |
| 12 | `12_resource_and_safety_hardening.md` | **no** | **BUILT 2026-08-25.** Explicit `keep_alive`, guarded flash-attention/KV benchmarking, watcher pre-emption, the registered `propose_file_diff` review tool, and interactive-vs-batch queue priority are implemented. |
| 13 | `13_image_storyboard_generator.md` | **Phase 0–3 control plane built; RealVisXL smoke verified 2026-08-25** | **Project core goal.** The exact approved RealVisXL V5 FP16 checkpoint is checksum-verified. A single approved isolated smoke render succeeded; the read-only graph planner is `work/image_render.py`, consent-gated no-GPU identity/LoRA planner is `work/character_library.py`, and `work/storyboard_from_story.py` enforces reference-overview approval before any frame plan unlocks. Actual image generation, training, identity-model installs, LLM decomposition, and storyboard expansion remain separately gated. |
| 14 | `14_queue_dropdown_ui.md` | **BUILT 2026-08-25** | Live media-queue **dropdown**: per-item status + progress, a ticking **timer**, the **waiting-on** reason (render busy / VRAM short / N ahead), and a **cancel** button (moves items to `cancelled/`). Builds on the 09 queue. |
| 15 | `15_vram_arbitration.md` | **no** | **Anti-deadlock.** A media job never stays stuck behind the chat LLM: reclaim ladder — coexist → **downgrade chat 14B→8B** → fully evict chat → run vision → reload. No mid-turn interruption; renders still always win. |
| 16 | `16_agentic_reasoning_execution_loop.md` | **no** | **BUILT THROUGH STAGE 5 (2026-08-24).** Durable checkpoints, source-labelled retrieval, inert local planning, offline harness evaluation, and explicit feedback are implemented. Real-task evaluation remains deferred. |
| 17 | `17_feedback_exemplar_video_actions.md` | approval-gated | **BUILT FOUNDATION 2026-08-24.** Privacy-preserving feedback, approved-only local Chroma/nomic retrieval, reversible exemplar lifecycle, and dense Qwen2.5-VL action coverage are implemented. Real operator evaluation cases remain opt-in; no external corpus is ingested. No MiniCPM. |
| 18 | `18_attention_runtime_optimization_backlog.md` | measurement-gated | **RESEARCHED 2026-08-24.** SageAttention v1/v2 are rejected for this RTX 5080 path and do not accelerate Ollama/llama.cpp. The guarded Ollama Flash Attention + q8 KV evidence harness and launcher-revision regression test are built; measure 14B only after that exact model is installed, then benchmark any future ComfyUI backend per workflow. |
| 19 | `19_vision_model_swap_nsfw.md` | **IDENTITY PINNED 2026-08-30** (see `CHANGELOG/2026-08-30_vision_model_nsfw_swap.md`, `notes/nsfw_vision_model.md`) | Watcher is pinned to exact `mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF` Q4_K_M + matching Q8_0 mmproj (SHA-256; llama.cpp, not Ollama). Live load unverified this session. **Qwen-Image-NSFW is a LoRA for `Qwen/Qwen-Image` — UPGRADE 13 has no clean gate** (RealVisXL `CheckpointLoaderSimple` only); identity recorded, not loaded. |
| 20 | `20_career_portfolio_evidence_pack.md` | no downloads initially | **FOUNDATION BUILT 2026-08-25.** Public-safe candidate git tree `local-agent-core` extracted and secret-scanned (0 findings); GitHub remote not created. Still pending: radio airtime, VLM VRAM timing, sanitized screen demo, human review before push. Codex still owns Sideband APK/`mesonpy`. |
| 21 | `21_general_project_scope_isolation.md` | no downloads | **BUILT 2026-08-28.** Workspace selection, read-only inspection, scope metrics, and reviewed operating-memory sections keep ordinary chats from inheriting Equal Shares state. New chats visibly choose Auto, General, or Equal Shares; the choice persists separately from model pinning. `inspect_workspace` classifies a supplied root without changing scope or permissions; fixtures cover code, dataset/LoRA, generic ComfyUI, and Equal Shares. The deterministic nine-case baseline has zero false specialist activations/tool exposures. |
| 22 | `22_loop_engineering.md` | no downloads for Phase 0 | **BUILT through guarded Phase 3 control plane 2026-08-28.** The controller is disabled by default, accepts only operator-created bounded goals, runs one fixed non-mutating check, redacts its audit, and cannot render, download, delete, change permissions, or self-certify completion. A repair can only queue an ordinary exact sidebar approval; a separate normal write must apply it, then the controller reruns one named check and halts after two identical post-repair failures. The optional CPU-only independent reviewer sees compact evidence only; malformed/unavailable review always becomes `needs_operator`, and its agreement output is not authorization. Live calibration remains explicitly gated. |
| 23 | `23_scheduler_live_and_import_hardening.md` | **no** | Import hardening **verified 2026-08-28**: missing ChromaDB/cryptography leaves agent and server importable with actionable capability status; all 12 scheduler safety/wiring tests pass. **Real phone delivery remains unverified** (requires an operator-side Sideband test). |
| 24 | `24_architecture_refactor_backlog.md` | **no** | **BUILT 2026-08-28.** Shared atomic writes cover all 14 audited writers; Chroma uses a guarded persistent-client singleton with a concurrency test; router CPU-pair fallback and CPU context policy are centralized; `agent.answer()` coordinates its five prefetch sources through `context_prefetch.py`; and row 12's stale `propose_file_diff` status is corrected. The multi-document status-chain ownership decision remains explicitly deferred. |

## Why this order

Prompt 1 matters more than the model swap. The agent currently asks the model to
emit `TOOL: name {json}` on a line by itself and parses it with a regex. That is
why a model can silently "forget" to use a tool and answer from memory — the
exact failure you saw with `qwen3:8b`. Ollama supports structured function
calling; models trained for it comply far more reliably than any amount of
prompt nagging.

Prompt 4 is the trick that makes the internet wait bearable: every sensory tool
gets **built, tested and registered now**, returning a clear "model not installed"
message. When the downloads land, nothing needs rewiring — the tools start
working.

## Downloads for prompt 5, so you can plan

```
gpt-oss-20b            ~13 GB    the main upgrade — MoE, ~3.6B active, tool-trained
nomic-embed-text       ~275 MB   retrieval over the docs
qwen2.5vl:7b           ~6 GB     vision, as a tool
faster-whisper large-v3 ~1.5 GB  audio, as a tool (pip, not Ollama)
```

Roughly **21 GB total.** Nothing before prompt 5 needs any of it.

## Where this is heading

`local_agent/ROADMAP.md` records the end goal: a **Reticulum mesh** linking phone
and workstation, so the same agent is reachable from an Android client with file
access — the phone as a thin terminal, all compute staying on the RTX 5080.

**Prompts 6a and 6 are the interim steps**, and 6a comes first for a reason:
`adb reverse` over a USB cable forwards the phone's own localhost to the
workstation's, so the server keeps binding `127.0.0.1` and nothing is exposed to
any network. It proves the entire mobile client — UI, streaming, auth, permission
tier — with the transport reduced to a physical cable. Prompt 6 then swaps the
cable for Tailscale.

`06b` is what makes it an *assistant on the phone* rather than a web page: a
Progressive Web App with a home-screen icon, Android share-sheet integration,
camera capture and voice. No Android development and no downloads.

**One dependency to know about:** PWA features need a secure context. Over 06a's
USB link the phone sees `http://127.0.0.1`, which qualifies — so build and test
06b there. Over Tailscale, `http://100.x.x.x` does **not** qualify, and 06 will
need `tailscale cert` / `tailscale serve` for real HTTPS before the installed app
works remotely.

All three build the same seam the mesh needs: **one predicate that decides whether
a session is remote.** USB answers it by token, Tailscale by source address,
Reticulum by cryptographic identity. Three transports, one function.

That end state is not built in these prompts, but it constrains them. Two rules to
preserve throughout: the HTTP server stays bound to **127.0.0.1**, and
`agent.answer()` stays **transport-agnostic** — it is the seam the mesh plugs
into. Read the roadmap before making an architectural decision.

## Prompt 7 stands apart

`07_batch_renderer.md` is not about making the agent smarter — it is a second
pipeline. Point it at a folder of numbered prompts, video motion references and
image reference slots, and it renders the sequence unattended.

It deliberately **reuses** the proven render path (`render_single_pass.py`,
`thermal_guard.py`, the queue owner, the duration ladder) and deliberately
**never touches** `outputs/equal_shares/**`. Two pipelines, one set of proven
settings, no shared state.

It can be run any time after prompt 1. It does not depend on 2–6.

## Rules that hold across all of them

- Never weaken a safeguard to make a test pass. `tools.py` stays a whitelist,
  the GPU-busy check keeps failing safe, the CPU thread cap stays at 4.
- Never start a render. Propose only.
- Never delete a raw generation, reference, manifest, audit record, or source
  audio.
- Every prompt ends with a `CHANGELOG/` entry: what changed, why, the evidence,
  what was verified, what remains unverified.
- `validate_h3_prompt.py` must still pass **124/124** after every one of these.
  If it doesn't, something upstream broke.

## Status & design notes

- `local_agent/UPGRADE/BUILD_STATUS.md` — built-vs-pending board for every prompt + live-verification list.
- `docs/design_notes/image_generation_strategy.md` — rationale for UPGRADE 13/19 (uncensored image, identity, storyboard).
- `docs/design_notes/architecture_review_response.md` — graded response to the external review (→ UPGRADE 12).
- `docs/design_notes/architecture_audit_2026-08-27.md` — full diagnostic audit of multimodal/tool-calling integration, Chroma memory efficiency, and CPU/GPU routing maintainability, with file:line evidence (→ UPGRADE 24).
- `docs/design_notes/distributed_compute_assessment.md` — the offload-to-a-second-box analysis (parked).
- `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md` — runbook/scripts/phased plan for the one-laptop-node step of `TODO.md`'s worker-farm bootstrap; cross-links the parked note above and the ten-node `WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md`. Nothing in it has run.
- `local_agent/UPGRADE/DRIVE_SOURCE_MANIFEST.md` — Google Drive provenance for the checked-in prompts.
