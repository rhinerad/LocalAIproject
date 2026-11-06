# Claude Code continuation — 2026-08-29

**Dated snapshot — the operator reprioritized on 2026-08-30: the local agent
is now general-purpose first, Equal Shares is a paused, optional project
profile. For current priorities read `local_agent/README.md`, `TODO.md`,
`docs/design_notes/architecture_audit_2026-08-27.md`, and recent
`CHANGELOG/2026-08-*.md` entries. The Phase 1 worker-farm state recorded
below is still historically accurate; treat "Current operator intent" below
as the intent as of 2026-08-29, superseded where it conflicts with newer
CHANGELOG entries.**

## Read first

1. `CLAUDE.md` — binding Equal Shares safety and verification rules.
2. `docs/LOCAL_AGENT_CURRENT_HANDOFF_2026-08-30.md` — current local-agent,
   phone, media, and worker-farm state.
3. `TODO.md` — authoritative remaining tasks.
4. `CHANGELOG/2026-08-29_phase1_worker_farm_foundation.md` — same-session
   evidence for the Phase 1 worker-farm changes.

## Current operator intent

- Keep the Equal Shares rendering pipeline paused. Do not start ComfyUI,
  render, download a model, or load a GPU model for this continuation.
- Continue safe local-agent and worker-farm implementation work. Do not claim a
  live worker-farm success until the bounded sample has actually completed.
- Never print or commit `.env`, Redis credentials, AES keys, raw export text,
  or decrypted artifacts.

## Phase 1 worker-farm status

The CPU-only, loopback-only foundation is at `local_agent/worker_farm/`. It
uses an isolated Python environment and supports only a benign, review-only
historical-export sample. It cannot render, invoke arbitrary commands, load a
model, promote Chroma/memory, or expose a network service beyond Redis bound to
`127.0.0.1`.

Completed and locally tested:

- AES-256-GCM encrypted artifact storage with fresh 12-byte nonces and
  authenticated read failure for malformed/tampered envelopes.
- Pre-encryption redaction of paths, email, named secret fields, bearer headers,
  URL credentials, and recognizable GitHub/Hugging Face tokens.
- 25 MiB input-size ceiling and 500,000-character review extraction ceiling.
- SQLite idempotency/lease state; failed broker publication returns a job to
  `staged`; transient worker `OSError` returns a job to `queued` for Celery's
  bounded retry.
- Celery accepts only authenticated `redis://` URLs at `127.0.0.1:6379` for
  databases 0 or 1.
- Read-only `RUN_PHASE1_DOCTOR.ps1` checks dependency/config shape, Docker
  engine access, and loopback Redis without revealing secrets or starting work.
- `Initialize-Phase1Secrets.ps1` refuses key replacement unless both
  `-Force` and `-AcknowledgeExistingArtifactsBecomeUnreadable` are supplied.
- `python -m unittest local_agent.worker_farm.test_farm_core -v` passed 12/12
  under `local_agent/worker_farm/.venv`.

## Live Phase 1 acceptance and next safe action

On 2026-08-29, Docker Desktop's stale runtime-socket failure was repaired by
preserving (renaming) only its transient runtime directories and reopening the
desktop engine. Docker then answered normally. The broker launcher also needed
Docker Desktop's installed credential-helper directory injected into its
*process-local* PATH; no system PATH or credential configuration was changed.
The Redis health check required the same locally held password inside the
container environment, so Compose was corrected and the loopback-only service
was recreated with its named volume retained.

The live bounded acceptance completed:

1. Redis is healthy and bound only to `127.0.0.1:6379`.
2. One Windows Celery worker is connected using the `solo` pool with
   `CUDA_VISIBLE_DEVICES=-1`; it registered only `distill_export`.
3. The synthetic fixture submitted as task
   `84dd6023-7f45-4ddb-b295-ebad819c7eb1` and completed as job
   `distill_5090ec5b50892412f0c1a04a`.
4. Metadata reports a `result_distill_*` artifact and the task returned exactly
   three `review_required` candidates. Artifact storage uses AES-256-GCM;
   raw fixture/result text was not printed or promoted.

No real ChatGPT/Claude export, model, GPU workload, render, Chroma write, or
memory promotion has been started. Do not submit a real historical export until
the operator explicitly chooses the source and authorizes staging it.

## Worker-farm task registration fix and Phase 1.5 plan (this session)

While reading `local_agent/worker_farm/*.py` to match existing patterns
before adding a new task, found and fixed a real bug rather than assuming
the existing pattern worked: `worker.py` launches Celery with
`-A local_agent.worker_farm.celery_app:app`, so the worker process only ever
imports `celery_app.py`, never `tasks.py`. Without `include=[...]` on the
`Celery(...)` constructor, `distill_export` was never registered on the
worker's own app — `submit_distillation.py` dispatches by name via
`app.send_task(...)`, not `.delay()`, so submission would have kept
succeeding while the worker silently discarded every job as unregistered.
Fixed with `include=["local_agent.worker_farm.tasks"]`. Verified with
Celery's own `find_app`/`import_default_modules()` against an isolated copy
(no live Redis needed — registration is decided by import wiring alone), with
a negative control confirming the new regression test actually fails on the
pre-fix code. Full local suite: 13/13. Not yet run against the real
`local_agent/worker_farm/.venv` on this machine — that is the closing step.
See `CHANGELOG/2026-08-29b_worker_farm_task_registration_fix.md`.

Also wrote `docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md` —
the runbook/scripts/phased plan for TODO.md's next concrete worker-farm step
("add the secondary laptop"), scoped to exactly one additional trusted node,
not the ten-node cluster in `WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md`.
Nothing in it has been run: no tunnel exists, no ACL user has been applied
outside this session's own reasoning, no laptop has connected. It cross-links
the parked `docs/design_notes/distributed_compute_assessment.md` (remote-chat
offload) as a related but separate, still-paused idea.

## PowerInfer evaluation boundary

`local_agent/powerinfer_openai_proxy.py` and
`docs/POWERINFER_CONTROL_PLANE_PLAN_2026-08-29.md` are an **unlaunched,
loopback-only evaluation scaffold**, not a replacement for Ollama. The adapter
passed four offline tests, but must not be wired into the launcher, picker, or
agent router until a matching sparse PowerInfer model, predictor, activation
assets, hashes/license, GPU-gateway grant, and measured RAM/VRAM/latency/quality
acceptance gates exist. Do not claim sparse acceleration for arbitrary Qwen,
Ollama, or normal GGUF models.

## Model Conversion & Profiling boundary

`docs/MODEL_CONVERSION_AND_PROFILING_PLAN_2026-08-29.md` is the mandatory
preparation/acceptance track for any candidate PowerInfer model, including an
abliterated model or post-LoRA merge. Upstream conversion expects matching
predictor weights and activation statistics; do not represent an arbitrary
checkpoint as automatically PowerInfer-convertible.

`tools/powerinfer/run_pipeline.ps1` is the native Windows runner (VS 2022 x64,
CUDA 12.8+, `LLAMA_CUBLAS=ON`, `sm_120`). The upstream source and isolated
Python environment are now present at `external/PowerInfer`; package imports
and CUDA 12.8 PyTorch availability were checked. Visual Studio 2022 Build
Tools with C++ is installed and the native CUDA/cuBLAS `sm_120` build completed
successfully through Ninja. The runner enters the VS 2022 developer environment
and uses `A:\PowerInferNative` (junction to source) and `A:\PowerInferBuild`
to avoid the canonical path-length failure; it preserves old failed caches.
No model, predictor, activation asset, server, or inference was started.
GPU/download/CMake work requires `-Execute`. The proxy still targets native
`127.0.0.1:8080`; no profile, conversion, or GPU load is authorized by
`-Stage show`.

### PowerInfer execution update — 2026-08-30

The approved ReluLLaMA-7B activation dump is now complete: all 32 layers have
their predictor-input data. The source tree combined SHA-256 is
`6bb8db502f6bec097eb7b67490edef5ec63bd4e57cd6b87cf31e6ebc4a514155`; the
8,000-document calibration JSONL SHA-256 is
`b8e285b6972c7fd64026c37596c84b1a388a90625ec78fc79030f03d357aa6f4`; and
the activation combined SHA-256 is
`a4d5a90f2b5cce2149250950ae12a74c00fa14816b08f86addb24c6486b6b518`.

Do not convert or launch the candidate. The original full training settings
were stopped after three batches because their duration had not been measured.
The runner now supports explicit bounded sample/rank/batch/epoch/layer ranges.
Layer 0's bounded 25k/rank-256/two-epoch calibration completed at 0.8593
recall and has been recorded in
`CHANGELOG/2026-08-30_powerinfer_bounded_predictor_calibration.md`. It is not
a complete predictor bundle or acceptance result. Continue with measured,
controlled batches only; retain the 82 C ceiling and verify that ComfyUI,
VLM/media, and any render are inactive before each batch.

The vault's large dump evidence is readable but not writable by the training
Python process on this Windows host. Do not move, delete, or rewrite it.
Use the explicit writable `-PredictorWorkspace`
`A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829`
for every subsequent predictor train/assemble/convert step. The runner now
defers assembly until all 32 layer files exist. Layers 1–4 have completed in
that workspace; layer 0 must be rerun there before a complete candidate set
can be assembled. See the 2026-08-30 changelog for exact calibration figures.

Update: layer 0 was rerun into the staged workspace, and controlled bounded
training completed layers 0–14. The operator explicitly resumed the remaining
layers: the active batch covers 15–19, and then the narrow guarded continuation
`tools/powerinfer/resume_calibration_guarded.ps1` handles absent layers 20–31,
one child process per layer. It starts only at <=70 C and force-stops the child
at 82 C. Assembly remains deferred until all layer files exist; no proxy/server
or model inference is authorized.

Completion update: all 32 staged predictor checkpoints and per-layer metrics
are now present, and the predictor assembled with `HASHES.json`. Aggregate
calibration recall was min/mean/max `0.7986` / `0.8262` / `0.8668`; this is
not an acceptance benchmark. The GPU returned idle at 30 C. Conversion,
quantization, model loading, validation, benchmark, registration, and serving
remain unstarted pending their distinct authorization and acceptance gates.

Latest update: F16 conversion, Q4 quantization, and packaging have completed
in the writable staging workspace. The candidate has passed one controlled
native sparse smoke validation: the matching PowerInfer venv was used to build
the GPU split, `2322.00 MiB` of FFN weights were offloaded, total VRAM use was
`6303.93 MiB`, and a coherent continuation was generated. The first failed
native attempt (system Python could not import `powerinfer`, so it offloaded
0 MiB) is retained as evidence. The candidate still must not be registered,
served, or connected to the local-agent picker: it requires a cold/warm
multi-turn benchmark and quality acceptance first. See the 2026-08-30
PowerInfer changelog for exact paths and measurements.

Benchmark update: `validation/acceptance_gate_20260830_175953.json` has passed
the mechanical acceptance gate. It records all 32 activation files, CUDA,
cached GPU-index application, 2322 MiB FFN GPU offload, and two 20-turn
loopback sessions with zero request failures (mean decode rate 110.729 cold,
100.743 warm tokens/sec). The test server was loopback-only and exited; GPU
returned to 33 C / 0% / 84 MiB. Preserve the earlier failed benchmark evidence.
The candidate remains isolated and unregistered: do not start a proxy, expose
it in the picker, or route agent traffic without an explicit quality-review and
promotion decision.

The quality-review gate is now prepared but unrun. Use the benign fixed packet
created by `tools/powerinfer/quality_comparison.py`, compare it manually against
an operator-selected current Ollama model and the separately approved loopback
candidate, then verify reviewer scores with the same script. This setup alone
does not authorize model loading or routing.

Quality capture update: the controlled sequential comparison against the current
`huihui_ai/qwen3-abliterated:8b` baseline completed, but the ReluLLaMA candidate
failed nine of ten elementary instruction/format cases. Preserve the captures
under `local_agent/runtime/powerinfer_quality_reviews/`; do not register, serve,
or expose this candidate. The likely next investigation is Llama-2 chat-template
or instruction-tuning alignment, followed by a fresh full review — not routing
it into the agent.

Cross-checked this pipeline (this session) against the earlier reply to
Grok's plan: evidence recording and native-build choices matched; `-VramBudget`
did not — it had a silent `12` default rather than being required. Fixed to
`[Nullable[double]]$VramBudget = $null` with an explicit throw inside
`Invoke-ValidateAndBench` (the only place it reaches a GPU binary) naming the
GPU-gateway/idle check. `-Stage show` and non-GPU stages are unaffected. Not
run through a real `pwsh` — no PowerShell in this sandbox. See
`CHANGELOG/2026-08-29d_powerinfer_pipeline_verification.md`. Independently
reran `test_powerinfer_pipeline.py`'s offline suite: 8/8, matching the
original claim.

## Pixel mobile PowerInfer-2 boundary

`docs/POWERINFER2_MOBILE_EDGE_PLAN_2026-08-29.md` is a planning-only correction
for the Pixel 10 Pro: it uses Tensor G5, not Qualcomm/Hexagon. The only current
upstream Android sparse guide is SmallThinker; it does not establish an NNAPI
or Tensor-TPU backend. `local_agent/worker_farm/termux_powerinfer2_edge_worker.py`
is an unlaunched, stdlib-only HTTPS gateway contract with offline tests. It
cannot reach Celery/Redis and must never receive the workstation Redis password
or AES key. No mobile binary/model was downloaded, compiled, or launched.

## Change discipline

Every change requires an immediate `CHANGELOG/` entry. Static tests and docs
are not render verification. Preserve unrelated working-tree changes and never
overwrite evidence or manifests.
