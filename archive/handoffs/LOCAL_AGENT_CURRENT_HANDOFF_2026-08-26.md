# Local Agent current handoff — 2026-08-26

## Read order

1. `CLAUDE.md` for binding safety rules.
2. This file for current local-agent state.
3. `local_agent/README.md` for architecture and operation.
4. `local_agent/UPGRADE/00_INDEX.md` for the upgrade backlog.
5. `local_agent/UPGRADE/20_career_portfolio_evidence_pack.md` for the
   portfolio checklist.
6. `CHANGELOG/` for verified change evidence.

## Current verified state

### 2026-08-30 — PowerInfer next-candidate research

ReluLLaMA-7B remains mechanically valid but failed 9/10 bounded
instruction/format quality checks, so it is not registered or routed. The next
candidate is the upstream Bamboo-DPO 7B dReLU sparse bundle; it remains
research-only until lineage, hashes, mechanical serving, and the same quality
gate pass. Existing Ollama routes remain unchanged.

The Equal Shares pipeline is paused. Do not start a render, load a model, or
resume a media job as part of local-agent maintenance.

The latest static regression pass did not load a model or start a render and
passed the structured native-tool suite (21/21), router switching (20/20),
GPU arbitration, exact-Qwen lazy-watcher protection, media pre-emption,
cross-chat retrieval, difficult-task routing, launcher parity, and the H3
validator (**124/124 valid**).

The GPU gateway is clean after regression: its live pending-card count is zero.
Native test requests are now isolated in temporary state, so future tests do
not pollute the operator-facing approval sidebar.

Recent local-agent upgrades now present in the working tree:

- **2026-08-28 workspace isolation completion:** chats retain a separately
  selected Auto, General, or Equal Shares workspace; `inspect_workspace` is a
  read-only 53rd tool that classifies an explicitly supplied root without
  changing scope or permissions. A deterministic nine-case scope baseline
  recorded zero false specialist activations and zero project-only tool
  exposures. Reviewed operating memory now has explicit General, Machine, and
  Project sections instead of keyword-based line deletion.
- **2026-08-28 GPU false-positive repair:** Windows may report the Codex/
  ChatGPT desktop application's display context in `nvidia-smi`. The router
  now ignores that same low-VRAM UI entry (as it already did browsers), while
  retaining blocks for ComfyUI, samplers, unknown compute owners, live queue
  ownership, port 8188, and material foreign VRAM use. A live check found the
  GPU idle at 81 MB with no resident Ollama model.
- **2026-08-29 GPU false-positive repair follow-up:** the idle `steam.exe`
  client is another low-VRAM WDDM display context, not an active game or
  render. The router ignores only that Steam launcher process below the normal
  material-VRAM threshold; ComfyUI's queue/port locks, unknown processes, a
  real game executable, and high VRAM use still reserve the GPU. Regression
  coverage confirms an idle Steam client no longer forces the CPU tier.
- **2026-08-28 guarded loop repair:** the disabled-by-default loop controller
  can queue, but never apply, a proposed text repair. A normal exact sidebar
  approval and write must happen first; a separate verifier then reruns one
  named check and halts after two identical post-repair failures. Its optional
  CPU-only reviewer receives compact evidence only and never grants authority.
- Context compaction and post-turn memory extraction use the exact CPU-host
  `llama3.1:8b` helper, never a GPU substitute. The model was downloaded and
  live-validated on 2026-08-28: strict structured compaction succeeded, the
  sensitive-input extraction test stored no fact, and `keep_alive="0"`
  released the model afterward. Routine regression tests mock this boundary so
  they cannot accidentally load a model.
- The low-priority 3D route is still configuration-gated. A read-only inventory
  found local TRELLIS image assets and a Hunyuan3D v2 checkpoint, but no 3D
  workflow JSON or node/API contract. A checksum-pinned future-contract
  validator is available, but no 3D tool or render is active.

- GPU permission gateway: ask/allow/block policy and one-shot approvals for
  agent-owned GPU model loads and render starts.
- Exact-content approval for configuration-like file writes (`.ini`, `.cfg`,
  `.json`, `.bat`, `.vbs`), while protected project records remain refused.
- Refresh-safe chat selection and local, non-authoritative cross-chat excerpt
  retrieval.
- A bounded 14B abliterated planning assist for difficult 8B conversations;
  it never replaces the pinned chat model and remains gateway-controlled.
- Paired-phone control remains default-deny. The active named Sideband identity
  has explicitly granted, revocable access to `start_current_chat_render`,
  `start_batch_render`, sandboxed `run_code`, fixed-whitelist `run_build`
  actions, and guarded `apply_hex_patch`; it still cannot edit text project
  files, stop processes, or alter memory. Binary patches remain exact-byte,
  one-shot desktop-approved actions and cannot touch Equal Shares evidence. Both
  render paths preserve
  all preflights, the global GPU Block control, and the append-only remote
  audit.

The currently running desktop process may still be the previous loaded code.
Apply these UI/server changes by restarting only the local-agent launcher at a
time when no response is actively streaming. Do not restart ComfyUI.

## Remaining work that requires an operator decision or controlled run

- **2026-08-29 PowerInfer evaluation:** a standard-library, loopback-only
  OpenAI-compatible adapter is implemented at
  `local_agent/powerinfer_openai_proxy.py` and has offline contract coverage.
  It is deliberately unlaunched and disconnected from existing routing.
  Upstream's sparse performance requires PowerInfer GGUF plus matched
  predictor/activation files; existing Ollama/Qwen models are not drop-in sparse
  candidates. `docs/POWERINFER_CONTROL_PLANE_PLAN_2026-08-29.md` defines the
  build, allocation, and acceptance gates. Do not claim 70B real-time behavior
  on the 16 GB GPU without a supported-model RAM/VRAM/latency benchmark.

- **2026-08-29 Model Conversion & Profiling:** PowerInfer model preparation is
  now tracked as a mandatory offline gate in
  `docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md`. Its first gate is
  compatibility evidence: upstream conversion requires matched predictor
  weights/activation data and does not prove a universal profiler for arbitrary
  dense, abliterated, or post-LoRA checkpoints. No model/profile/conversion has
  been run. Candidate models stay on their existing normal route until an
  accepted lineage and validation manifest exist.
- **2026-08-29 PowerInfer production registry gate:** a model cannot enter the
  separate PowerInfer registry or start its loopback OpenAI proxy without a
  human-registered, revalidated `accepted` supported-sparse manifest, complete
  acceptance evidence, and matching GGUF hash. This adds no automatic routing:
  ordinary Ollama remains the active path until a later explicit deployment.
- **2026-08-29 PowerInfer prerequisite audit:** CUDA 12.8, RTX 5080 driver
  595.97, and Visual Studio C++ tools are present; Visual Studio's bundled
  CMake exists but is not on normal PATH. The PowerInfer source checkout and
  sparse model artifacts are absent. This was read-only: no build, download,
  model load, or GPU work occurred.

- **2026-08-29 Pixel mobile PowerInfer-2 evaluation:** the phone is Google
  Tensor G5/TPU hardware, not Qualcomm/Hexagon. Upstream's currently documented
  Android sparse runtime is SmallThinker; no Tensor/NNAPI execution path is
  verified. `docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md` and the inert
  `local_agent/worker_farm/termux_powerinfer2_edge_worker.py` define a safe
  cross-build and future gateway contract. No Android build/model/runtime was
  downloaded, compiled, launched, or connected to Redis. Direct workstation
  Redis/AES credentials on the phone remain prohibited.

- **2026-08-29 local-agent regression repair:** the optional CPU context
  compactor was being asked to summarize framework inserts/one-message turns
  under static-prompt pressure, creating avoidable long CPU waits. It now runs
  only for meaningful older conversation and is bounded to 12 seconds. The
  busy-GPU model picker now correctly retains the operator-requested 14B as a
  visible disabled entry at fresh busy startup. The core loop, routing,
  workspace, media, phone, and worker-farm test groups passed; H3 validation
  remains 124/124.

- **2026-08-29 scheduled phone delivery repair:** the bridge had hard-coded
  direct-link LXMF delivery, so a live six-message schedule was submitted but
  not received after the immediate phone link had closed. The bridge now uses
  Sideband's ratchet-aware opportunistic fallback and writes final delivery or
  failure callbacks to `runtime/lxmf/outbound_delivery_audit.jsonl`. Restart
  the bridge and perform one short phone receipt test before claiming the fix
  live-proven.

- **2026-08-29 radio metrics instrumentation:** `radio_metrics.py` and the
  controlled receipt protocol are ready. The existing audit contains 111
  unique LXMF queue events but no phone-receipt evidence, so it correctly
  reports delivery as unmeasured; never treat that count as received messages.
  The local metrics and scheduler regression suites pass. A controlled phone
  test with receipt timestamps and an explicit close time is still required
  before packet-loss or latency claims.
- **2026-08-29 Worker Farm Phase 1 foundation:** a CPU-only, loopback-only
  Redis/Celery skeleton now exists at `local_agent/worker_farm/`. The only
  job is a benign sample historical-export distillation that produces encrypted
  `review_required` candidates and cannot promote Chroma/memory, render, run
  commands, load a model, or expose the broker. Its local safety coverage now
  has 12/12 passing checks, covering AES-GCM tamper refusal,
  sanitization, local-only broker URL enforcement, retryable queue states, and
  no-secret diagnostics. Celery/Redis client are installed in an isolated
  `.venv`, Docker Desktop 4.88.1 is installed, and a generated local `.env`
  has valid secret field shapes. This Codex sandbox account cannot access
  Docker's local engine reliably: the guarded probe timed out before Redis
  could start. Wait for Docker Desktop to show **Engine running**, then launch
  the guarded live sample from the normal Windows desktop account. It remains
  unverified; no broker or worker has been started here. See
  `local_agent/worker_farm/README.md`.
  **Historical (2026-08-29).** Live farm Redis on DuranGamingPC is Ubuntu-24.04
  Docker CE (`FARM_REDIS_ENGINE=wsl`, `2026-09-03bg`/`bh` / `2026-09-04a`).
  Waiting for Docker Desktop **Engine running** is the **Desktop rollback
  path only, not the live default.**
- **2026-08-29 worker_farm task-registration fix:** `worker.py`'s actual
  Celery load path (`-A local_agent.worker_farm.celery_app:app`) never
  imported `tasks.py`, so `distill_export` was never registered on the real
  worker process — every job submitted by `submit_distillation.py`'s
  name-based `send_task(...)` would have been silently discarded as
  unregistered. Fixed with `include=["local_agent.worker_farm.tasks"]` in
  `celery_app.py`; added a subprocess-based regression test (an in-process
  version was tried first and caught giving a false pass, so it was replaced)
  that reproduces `worker.py`'s exact load path. 13/13 local tests pass; not
  yet run against the real `.venv` on this machine. See
  `CHANGELOG/2026-08-29b_worker_farm_task_registration_fix.md`.
- **2026-08-29 Worker Farm Phase 1.5 plan:** wrote the runbook, scripts
  (`relay/tunnel_relay.py`, `Add-Phase1SecondaryWorkerCredential.ps1`), and
  phased plan for adding one additional trusted worker node (the operator's
  laptop) over a WireGuard tunnel and a scoped Redis ACL credential — the
  concrete next TODO.md step, not the ten-node cluster. See
  `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md`. Nothing in
  it has run; the Redis ACL rule and the relay's forwarding logic are
  reasoned/unit-tested in isolation but not proven against a live Celery
  worker, and the plan says so explicitly.
- **2026-08-28 phone attachment scope repair:** a paired-phone image was
  received, copied into the immutable LXMF upload path, and sent to the
  `see_image` tool; no render tool was called. The reply nevertheless repeated
  an unrelated old render-permission topic from a stale task checkpoint. Direct
  unrelated requests now supersede the old checkpoint without deleting it, and
  receive a turn-local scope boundary. Regression coverage passes together
  with the 14 scheduler tests. The local-agent server was restarted with this
  repair; resend the attachment question to validate the live bridge response.
- Complete the remaining Sideband scheduler acceptance: cancel a second active
  run mid-way and test a bridge restart while a schedule is active. The paired
  phone completed and received a five-message, 15-second counter schedule on
  2026-08-28, so the phone → bridge → CPU agent → scheduler → LoRa reply path
  is now live-proven. The counter-only default and queued-counter audit label
  were corrected afterward. The local-only scheduler suite is 14/14 and
  optional-import hardening is 22/22.
- Run the radio delivery experiment and collect real packet-loss/latency data.
- Design and run a cold-cache Qwen2.5-VL lifecycle protocol before publishing
  process-start/cold-load numbers. Three exact-pair runs succeeded and released
  VRAM to 0 MB, but warm caches caused materially different startup timings; see
  `CHANGELOG/2026-08-26_qwen25_vl_lifecycle_benchmark.md`.
- Make a public-safe demo recording using a licensed benign asset, then human
  review every frame for private data.
- Choose and configure a public GitHub remote only after human review of the
  pre-extracted public-safe tree.
- Resolve the Sideband Tier B Android `mesonpy`/NumPy toolchain blocker before
  claiming any custom APK feature.
- Consider the guarded Ollama Flash Attention + `q8_0` KV-cache benchmark only
  after explicit approval and when no GPU owner is present.

- **2026-08-29 Worker Farm Phase 1 live bounded acceptance:** Docker Desktop's
  stale runtime AF_UNIX socket failure was repaired by renaming only the
  transient `Docker/run` and `docker-secrets-engine` directories, then reopening
  Docker; no Docker image, container, or volume was reset. The Phase 1 launcher
  now adds Docker Desktop's already-installed credential helper to its own
  process PATH, and the Redis health check receives the existing container-local
  password. Redis is healthy on `127.0.0.1:6379`; one `CUDA_VISIBLE_DEVICES=-1`
  Celery solo worker registered `distill_export`; and the synthetic fixture
  completed as `distill_5090ec5b50892412f0c1a04a` with an encrypted result
  artifact and three `review_required` candidates. No real private export,
  Chroma/memory promotion, model, GPU workload, or render ran. The next action
  requires explicit operator source selection/authorization for any real export.

- **2026-08-29 encrypted archival and Pixel model decision:**
  `docs/ENCRYPTED_ARCHIVAL_RUNBOOK.md` defines the approved client-side
  encrypted, versioned archive design for raw media/evidence/large artifacts.
  It has not initialized a destination or touched any data; the first archive
  still requires the operator's destination, recovery-secret, source-root, and
  restore-drill choices. The intended Pixel PowerInfer target is the exact
  upstream `SmallThinker-21B-A3B-Instruct.Q4_0.gguf`; the exact 4B Q4_0 model
  remains a required runtime/thermal smoke test only. Neither model nor a phone
  binary has been downloaded or run, and Tensor/NNAPI acceleration remains
  unproven.

## Portfolio wording boundary

The RNode/LXMF path is experimental until multi-session delivery metrics and
device tests exist. The exact VLM is lazy and guarded, but its measured load
and release latency is not yet established. Never turn static tests into live
performance claims.
