# Local Agent — current handoff (2026-08-25)

## Scope now

The Equal Shares render/audio pipeline is deliberately **paused**. Its stalled
ComfyUI backend was stopped on 2026-08-25 only after the operator explicitly
requested it: the normal interrupt did not release the confirmed idle listener.
Do not start, resume, or monitor the pipeline as part of local-agent work. Its
safeguards and evidence rules remain intact, but `local_agent/` is now being
evolved as a general local desktop assistant rather than an Equal Shares-only bot.

The canonical working tree is this handoff folder. The parent `outputs/` tree is
a stale fork and must not receive state copies or be used as a source of truth.

## Verified desktop-agent state

- Native Ollama function calls with schemas, multi-call tool hops, and legacy
  text-protocol fallback are implemented.
- The GUI supports persistent chats, model-per-chat selection, attachments,
  media queue visibility/cancellation, stop/render controls, and 127.0.0.1-only
  HTTP.
- GPU/CPU routing protects the 16 GB GPU: a render wins; media yields; the
  interactive reasoning path can fall back rather than layer-offloading.
- The exact primary chat model `huihui_ai/qwen3-abliterated:14b` is installed.
  When port 8188 indicates ComfyUI owns the GPU, the agent intentionally does
  **not** poll the GPU Ollama catalogue; it uses the dedicated CPU
  `huihui_ai/qwen3-abliterated:8b` path instead. This avoids stale connection
  churn while retaining a clear refusal for a GPU-only pinned model. During
  that state, the new-chat model picker shows only the actually usable 8B
  option rather than offering a misleading CPU-hosted 14B entry.
- The local VLM remains lazy/on-demand. It is not a resident chat model. Visual
  work is pinned exclusively to the verified exact pair
  `Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf` (4.68 GB) and its matching
  `Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf` (0.73 GB). It runs
  only through the watcher-owned CUDA llama.cpp runtime; it never substitutes
  the older Ollama Qwen3-VL model.
- A controlled live image caption validated that exact pair through the local
  CUDA llama.cpp runtime on 2026-08-25. The diagnostic recorded only model and
  result-integrity metadata, then released the VLM and returned the GPU to idle.
- URL fetching, local image/video/audio analysis, local transcription when an
  installed model exists, and retention/retrieval/memory safeguards are present.
- Coding mode is a model-picker choice (default
  `huihui_ai/qwen2.5-coder-abliterate:14b`). `run_code` executes only under
  `local_agent/sandbox/run_<id>/` (CPU, timeout/output caps, network off by
  default, phone default-denied). A live 14B-coder GPU session is still
  unverified; the launcher does not pull that model unless
  `-EnsureCodingModel` or `EQUAL_SHARES_ENSURE_CODING_MODEL=1`.
- The Sideband Tier A phone bridge is implemented and has completed one real
  paired stock-Sideband round trip. Its desktop GUI remains unchanged and remote
  identities remain default-denied for privileged tools. Tier B source overlay
  and custom Android packaging work are in progress; neither a custom APK nor
  phone-camera/media acceptance has been claimed as complete.

## General storyboard path

1. **RealVisXL V5 FP16** is installed and checksum-verified. One explicitly
   approved isolated 1024×1024 smoke image completed, passed visual inspection,
   and released the GPU.
2. `plan_story_image` prepares an inspectable t2i/i2i graph only. It never
   loads the checkpoint, starts ComfyUI, uses GPU, or creates an output.
3. `work/character_library.py` provides a no-GPU LoRA training plan and an
   adult-consent-gated character registry. It cannot invoke kohya_ss or train.
4. `work/storyboard_from_story.py` validates the character/shot plan and
   persists a **reference-overview approval gate**. Reference sheets must be
   recorded for every character and explicitly approved before the read-only
   frame plan unlocks.
5. The desktop agent exposes that same storyboard sequence. Phone identities are
   default-denied for its state-changing operations. Nothing in this path starts
   an image/video render without a separate explicit operator request.

## Explicitly deferred gates

- Operator-written, anonymized real-task evaluation cases. The harness is ready,
  but it deliberately cannot mine chats or invent benchmark assertions.
- Operator review of any staged exemplar or feedback rule. Pending material never
  enters memory or retrieval without that review.
- The matched 14B GPU KV-cache measurement. It requires an explicit model-load
  approval and remains off by default until baseline/candidate reports match.
- Real image generation beyond the one smoke render.
- kohya_ss training, InstantID/IPAdapter/PuLID installs, and identity-model
  downloads.
- LLM-driven story decomposition against a live model.
- Vision QC of actual storyboard frames and any video render.
- Sideband Tier B Android packaging and phone file/camera/microphone integration.

Ask before any of those causes a download, model load, training run, image
generation, or video render.

## KV-cache experiment

`START_LOCAL_AGENT_GUI.ps1` keeps the normal Ollama cache mode by default. An
explicit, GPU-only `-GpuKvCache flash_q8` candidate exists, but is **not
enabled**. Preliminary exact-completion measurements showed 10,361 MB resident
VRAM for the candidate versus 11,859 MB for the corrected baseline; their
startup states were different, so a matched idle-GPU run is still required
before changing the default. Never perform that run while ComfyUI is active.

## Last verification

- `python work/test_image_render.py` — 6/6 passed.
- `python work/test_character_library.py` — 4/4 passed.
- `python work/test_storyboard_from_story.py` — 4/4 passed.
- `python local_agent/test_story_image_plan.py` — 5/5 passed.
- Full local-agent suite — 155 tests passed.
- Exact live caption diagnostic — available through the exact local model and
  `llama.cpp`; non-empty result (334 characters), metadata hash
  `f14e1cf6f6759257f8f7c5e4cd1c1c5537e76521502ac2debab9202bf8dd6c9a`, then
  released. Metadata-only report:
  `local_agent/runtime/benchmarks/qwen25_vl_caption_live_2026-08-25.json`.
- `python local_agent/agentic_eval.py` — 5/5 passed, mocked/no model load.
- `python local_agent/test_h3_evaluation.py` — 1/1 passed.
- `python local_agent/h3_evaluation.py --dir outputs/equal_shares/prompts_native_r2v`
  — 124/124 valid, 1.645 s, privacy-safe aggregate report and four detected
  synthetic negative controls.
- Portfolio evidence foundation: `docs/adr/` contains five decision records and
  `docs/portfolio/architecture_overview.md` contains sanitized architecture,
  GPU-lifecycle, and remote-permission diagrams. Measurement and public-demo
  work remain pending. `docs/portfolio/validation_matrix.md` is the canonical
  command/result index and deliberately separates source checks from device or
  performance claims.
- Portfolio license triage is recorded in
  `docs/portfolio/dependency_license_inventory.md`. Sideband-derived code stays
  private: the bundled Sideband source is CC BY-NC-SA 4.0 and its bundled LXST
  component is CC BY-NC-ND 4.0. No public repository extraction is authorized.
- `local_agent/measure_qwen25_vl_lifecycle.py` provides the exact-VLM lifecycle
  measurement harness. It is plan-only by default; `--execute` remains an
  explicit model-load gate and was not used in this session.
- The separate local-only `local-agent-core` portfolio candidate passed 10/10
  synthetic tests and the release audit with zero findings. It has no remote
  publication configured; the canonical handoff remains private.
- `python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v` — 124/124 valid.
- Current no-GPU regression pass (2026-08-25): native tool calling 19/19,
  H3 harness 1/1, LXMF bridge 11/11, and Sideband Tier B source 4/4. The
  public-release boundary is `docs/portfolio/public_release_boundary.md`; it is
  a plan, not an authorization to publish. Its non-destructive audit helper
  (`local_agent/public_release_audit.py`) passed 2/2 regression tests and found
  no issues in the current ADR directory.

## Read order

1. `CLAUDE.md` for binding safety rules.
2. This document for current local-agent state.
3. `local_agent/README.md` for architecture and operation.
4. `local_agent/UPGRADE/00_INDEX.md` for the upgrade backlog.
5. `CHANGELOG/` for change evidence.
# 2026-08-25 continuation note

## CPU fallback resilience

The CPU-safe chat route now uses a 16,384-token window. The former 8,192-token
setting was structurally too small for the always-on policy and native tool
schemas (about 9,600 tokens before the operator request). While ComfyUI owns
the GPU, optional structured planning is skipped and the deterministic task
record continues without a second CPU inference or timeout note. Oversized tool
evidence is clipped deterministically after history compaction. See
`CHANGELOG/2026-08-25_cpu_fallback_context_resilience.md`.

The model picker retains a last-verified GPU capability label while ComfyUI is
busy, so a dual-tier Huihui model is no longer misleadingly shown as “CPU
only.” This affects display only; routing still switches to CPU immediately
when the GPU is owned.

The desktop chat now includes a live, expandable work trace. It reports actual
route, evidence, tool, and drafting milestones without revealing raw hidden
chain-of-thought.

This was static/regression-verified only: no model was loaded and no render was
started. If port 11435 is absent, the desktop launcher still needs to be run to
start the CPU-only Ollama server; do not use a model pull or load without
operator approval.

## Deep Search and action integrity

The current desktop server revision is
`2026-08-25-action-integrity-r58`. Deep Search remains a bounded, read-only,
multi-source research tool. Its synthesis treats webpage content as untrusted
evidence, not instructions, and removes any citation URL the system did not
actually fetch. It keeps up to 6,000 characters of its bounded result for the
follow-up answer; ordinary tool evidence remains capped at 2,400 characters.

The newest prior chat contained unverified claims that third-party software had
been downloaded, opened, and modified. There were no tool events or tool
results in that chat, so none of those claims count as completed work. The
agent now refuses access-control bypass requests before model inference and
will replace an unsupported “I did it” claim with an explicit statement that no
verified local action happened. The server stores concise tool-result evidence
in the assistant message metadata for later audit. Live tool cards remain the
operator-facing proof during a response.

Regression evidence: native tool calling 21/21, Deep Search 6/6, search backend
7/7. No model was loaded, no download occurred, and no render was started.
See `CHANGELOG/2026-08-25_deep_search_and_action_integrity.md`.

## Direct file-task authorization

As of server revision `2026-08-26-direct-file-task-r59`, an explicit desktop
request to complete a normal file-editing task is sufficient authorization for
the agent to read, edit, and verify that text file. A separate diff-preview and
second confirmation are no longer required; request a preview explicitly when
desired. Protected manifests, evidence records, queue ownership files, render
guards, and phone default-deny rules are unchanged. See
`CHANGELOG/2026-08-26_direct_file_task_authorization.md`.

## External dataset evaluation staging

Dataset review found that OpenHermes 2.5, FineWeb-Edu, and The Stack v2 should
not be randomly injected into live Chroma retrieval; ScribeAgent's main
workflow data is proprietary. The only qualified use is UltraFeedback as a
reviewed, offline preference-evaluation source. The plan-only staging adapter
is `local_agent/stage_ultrafeedback_eval.py`; it defaults to no network and
needs `--execute` for the explicit Hugging Face download gate. It never embeds
or activates records. See
`CHANGELOG/2026-08-26_ultrafeedback_evaluation_staging.md`.

## Sideband Tier B Android build

The isolated WSL debug build remains **in progress / not installable**. It has
cleared the missing host-Python pip helper, but the pinned
python-for-android NumPy recipe fails because its isolated build environment
cannot import `mesonpy`. No APK was produced and no desktop, GPU, ComfyUI, or
Equal Shares work was started. See
`CHANGELOG/2026-08-25_sideband_tier_b_android_build_status.md` for the exact
status and next safe action.

NumPy is required by Sideband's local audio-processing source and was not
removed. A staged local recipe overlay was loaded but did not change the
isolated `mesonpy` import failure; do not repeat that retry without changing
the underlying toolchain or using a proven compatible NumPy recipe.

# 2026-08-25 Grok coordination

Grok took documentation-only upgrade-20 items and left Codex the Android
NumPy/`mesonpy` build. Read `GROK_STATUS.md` and
`CHANGELOG/2026-08-25_grok_portfolio_evidence_docs.md`. ComfyUI was still
listening on 8188 during that session; do not start a VLM or render to check.

A public-safe candidate git tree now exists at home-directory `local-agent-core`
(outside this folder). Secret/path scan: 0 findings. See
`CHANGELOG/2026-08-25_grok_public_tree_extract.md`. Do not merge that tree into
this working copy. No GitHub push was made.
