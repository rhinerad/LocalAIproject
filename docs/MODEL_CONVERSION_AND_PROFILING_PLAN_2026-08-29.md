# Model Conversion & Profiling — PowerInfer preparation track

## Purpose and current compatibility boundary

This track is the mandatory, offline preparation path for models proposed for
the PowerInfer control-plane endpoint. It covers base checkpoints, abliterated
derivatives, and post-LoRA merged checkpoints as candidate inputs. It does not
authorize a download, merge, profile, conversion, GPU load, or deployment.

The desired artifact layout is a model-specific bundle containing:

```text
<model-id>/<build-id>/
  source/                 # immutable source manifest + hash; not a duplicate model by default
  calibration/            # license-approved, sanitized, versioned calibration manifest
  activation/             # layer activation profiles; never mixed between model revisions
  predictor/              # predictor weights matched to the exact architecture/revision
  output/<model>.powerinfer.gguf
  output/<model>.q4.powerinfer.gguf
  validation/             # prompt set, raw measurements, report, hashes
  manifest.json           # lineage, tool commits, hashes, license, acceptance state
```

## Non-negotiable compatibility gate

The official PowerInfer conversion procedure takes **original compatible model
weights plus compatible predictor weights** and produces a `.powerinfer.gguf`.
PowerInfer lists a limited set of supported sparse families and says normal
llama.cpp-compatible weights receive no sparse performance gain. The inspected
documentation does not establish a maintained, general-purpose offline solver
that creates trustworthy predictor weights for every arbitrary dense,
abliterated, or post-LoRA checkpoint. See the [upstream PowerInfer README](https://github.com/Tiiny-AI/PowerInfer).

Therefore the pipeline has two routes:

1. **Supported sparse route:** exact architecture/revision with an upstream or
   independently validated predictor and activation-statistics source. Convert,
   quantize, and validate.
2. **Research route:** an otherwise unsupported model is catalogued and tested
   for a documented profiler/predictor-training method first. If no supported
   method, it remains an Ollama/llama.cpp candidate; it is not labeled or
   deployed as a PowerInfer model.

No predictor, activation profile, GPU index, calibration result, or final GGUF
may be reused across base revisions, quantizations, abliterated variants, or
post-LoRA merges without a documented evidence-backed compatibility result.

## Standard offline pipeline

### Stage 0 — intake and eligibility

1. Assign immutable `model_id` and `build_id`; record source repository,
   revision/commit, architecture, license, model card, and SHA-256 for every
   input shard.
2. Classify input as `base`, `abliterated`, or `post_lora_merge`; record merge
   tool/version and adapter hashes for the last category.
3. Check the architecture against PowerInfer's supported sparse route and
   identify the exact predictor/activation provenance. Fail closed to the
   normal runtime when absent.
4. Reserve a controlled GPU-gateway window. The RTX 5080 must have no ComfyUI,
   VLM, render, or interactive-chat owner before profiling begins.

### Stage 1 — immutable staging and calibration contract

1. Keep source weights read-only after hashing. Never edit a source shard in
   place.
2. Create a calibration manifest, not an unreviewed data dump: source/license,
   redaction status, prompt IDs, expected language/domain mix, and hash.
3. Exclude personal chats, private creative work, credentials, protected story
   assets, and unlicensed corpora. Use a small approved calibration set first.
4. Pin the profiler/converter commit, Python environment lock, CUDA/driver
   version, and hardware inventory in `manifest.json`.

### Stage 2 — profile or obtain predictors

1. For the supported route, obtain matching predictor weights and activation
   files with hashes and license evidence.
2. For the research route, run only a separately approved, documented
   predictor-training/profiling implementation on the pinned calibration
   manifest. Treat its outputs as experimental until the validation gates pass.
3. Store activation files under the build-specific directory. Never overwrite
   prior profiles; a changed calibration manifest creates a new build ID.
4. Record wall time, peak VRAM, peak system RAM, disk I/O, tool output status,
   and any numerical errors. A failed profile is quarantined with metadata, not
   promoted or silently retried with different data.

### Stage 3 — convert, quantize, and package

1. Convert only the exact input/predictor pair to `<model>.powerinfer.gguf`.
2. Produce Q4_0 only where the pinned runtime supports it; retain source and
   conversion logs separately from the production artifact.
3. Generate an artifact manifest containing parent hashes, converter command
   fingerprint (arguments without secrets), output SHA-256, size, quantization,
   and expected runtime/version.
4. Keep generated GPU-index files and runtime caches in `runtime/`, not under
   the immutable output bundle; delete none automatically.

### Stage 4 — offline validation and release decision

1. Run deterministic smoke prompts and a fixed held-out coherence suite against
   both source baseline and converted candidate using equivalent sampling. The
   initial local implementation is `tools/powerinfer/quality_comparison.py`:
   it prepares ten benign reviewer-scored cases without starting either model,
   and verifies the completed score record separately.
2. Measure cold start, warm start, prompt throughput, decode throughput,
   peak VRAM, peak RAM, GPU/CPU utilization, and error/restart rate.
3. Inspect tool-call JSON, multilingual/long-context outputs where relevant,
   refusal behavior, and character/LoRA regression prompts where relevant.
4. Promote only an accepted manifest to the loopback PowerInfer registry. The
   proxy remains unlaunched until the GPU gateway is approved for the specific
   test.

## Storage and lifecycle policy

| Class | Location | Rule |
|---|---|---|
| Source checkpoints | dedicated model vault outside the repository | hashed, read-only, no duplicate copies unless explicitly needed |
| Calibration manifests | repository metadata | sanitized, licensed, no private raw text |
| Private calibration/result content | encrypted artifact store outside repository | AES-256-GCM; access logged; never commit |
| Activation/predictor outputs | model vault per `model_id/build_id` | immutable once validation begins |
| Final GGUFs + manifests | model vault `production/` or `quarantine/` | only manifest-accepted builds may enter production |
| Logs/caches/GPU indexes | runtime scratch location | bounded retention, no automatic evidence deletion |

Budget before a run: free disk must cover source weights, profile/predictor
artifacts, final GGUF, temporary conversion workspace, and a 20% safety margin.
The staging process must refuse rather than overwriting an existing bundle.

`tools/powerinfer/init_vault.py` implements that layout. Preferred root is
`D:\PowerInferModels` (outside the git tree). It creates `production/`,
`quarantine/`, `scratch/`, `private/`, and `keys/`, plus per-build
`source/`, `calibration/`, `activation/`, `predictor/`, `output/`,
`validation/`, and `runtime/`. `preflight` refuses when free disk is below
need plus 20%. `protect-source` hashes then marks shards read-only.
Private calibration/results are AES-256-GCM envelopes under `private/` with
an append-only `access.log`. There is no delete path for conversion
evidence. The runner in `run_pipeline.ps1` is not yet required to call this
tool on every stage.

## Native runner (opt-in, unlaunched)

`tools/powerinfer/run_pipeline.ps1` is the Windows orchestrator for this track.
It parameterizes two targets in `tools/powerinfer/models.json`:

- `prosparse-7b` — supported-sparse proof of concept (`f=11008`, SentencePiece).
- `llama31-8b-abliterated-relu` — research route after ReLUfication (`f=14336`,
  `--vocabtype bpe`). SiLU abliterated Llama-3.1 checkpoints fail `relu-gate`.

Dump, train, convert, quantize, package, and the 20-turn acceptance gate are
shared. GPU/download/CMake work requires `-Execute`. The runner does not promote
a bundle to the interactive picker. Live compile and benchmark numbers are not
established until that execute path is run on an idle RTX 5080.

## Dependency links

### A. Real-time interactive Control Plane

No model may be listed in the PowerInfer proxy/model picker until its accepted
bundle manifest, sparse compatibility evidence, baseline comparison, and
GPU-gateway approval exist. Existing Ollama models remain unchanged.

### B. Harmon Town Nothing Forever character LoRA stage

After an approved LoRA merge: create a new candidate build ID and repeat
Stages 0–4. A base model's predictor/activation set cannot be assumed valid for
the merged character model. Until it passes, use the existing normal inference
route rather than blocking character work on experimental conversion.

### C. Judge evaluation loop

The Judge queue may reference only a registry-approved PowerInfer model by
immutable build ID. Batch workers do not perform conversion or profile a model
while handling user data. An unaccepted candidate stays out of the judge
fallback/routing table.

## Production acceptance checklist

- [ ] Source, adapter/merge (if any), calibration manifest, predictor,
  activation profile, converter, and final GGUF all have verified SHA-256
  lineage in one manifest.
- [ ] Architecture and runtime compatibility is evidenced; no unsupported dense
  checkpoint is represented as sparse PowerInfer-ready.
- [ ] License/provenance for weights, predictor, and calibration source is
  documented and acceptable.
- [ ] Conversion completed without numerical/converter errors; output loads in
  the exact pinned PowerInfer build.
- [ ] Baseline versus candidate held-out prompts meet the declared coherence,
  instruction following, tool-call, and character-consistency threshold.
- [ ] Cold/warm latency, decode rate, VRAM/RAM peak, GPU/CPU utilization, and
  failure rate are recorded under the same hardware conditions.
- [ ] Candidate does not interfere with ComfyUI, VLM, render, or active chat;
  the GPU gateway approved the controlled test and resources are released.
- [ ] Human reviewer accepts the evidence report; registry status changes from
  `candidate` to `accepted`. Otherwise it remains `quarantine` with its logs.
