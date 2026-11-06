# 2026-08-30 — PowerInfer bounded predictor calibration

## Completed controlled work

- The approved ReluLLaMA-7B activation dump completed before this entry. It
  generated the complete predictor-input set for all 32 layers and returned the
  RTX 5080 to an idle state afterwards.
- The initial upstream training defaults were deliberately stopped after three
  batches: 400,000 samples, rank 1024, batch size 1024, twenty epochs over 32
  layers would have made an unmeasured multi-day commitment. No raw predictor
  output was accepted from that stopped attempt.
- `tools/powerinfer/run_pipeline.ps1` now makes bounded training explicit with
  `TrainSamples`, `PredictorRank`, `TrainBatchSize`, `TrainEpochs`,
  `LayerStart`, and `LayerCount`. It validates the selected range and prints
  the effective training plan.
- A single controlled layer-0 calibration completed with 25,000 samples,
  rank 256, batch 256, and two epochs. The saved best model was
  `predictor_raw/layer0-0.8593-5002.pt`; its recorded held-out values are:
  loss `0.20933188498020172`, recall `0.8593054263240327`, predicted active
  neurons `5001.72744140625`, true active neurons `3013.54482421875`.

## Windows vault write boundary and staged calibration

- The existing `A:\PowerInferModels` vault permits reading the 360+ GiB dump
  evidence but rejects ordinary new-file writes from the PowerInfer Python
  process, including after a narrow ACL grant to its `predictor_raw` directory.
  The failed layer-1 attempts created no retained partial checkpoint. No source,
  activation, or existing layer-0 result was changed.
- The runner now accepts `-PredictorWorkspace` for the small, writable
  checkpoint/predictor artifacts while keeping the large source, calibration,
  activation, and predictor-input evidence in the original vault. This is a
  path reference, never a move/copy/delete mechanism. Its conversion stage uses
  the same workspace explicitly.
- `init_vault()` is now idempotent after first creation: it preserves existing
  `.gitignore` and `vault.json` rather than rewriting evidence/configuration on
  each execute stage. The trainer also refuses checkpoint replacement and
  retries only a transient failed write while the target is still absent.
- The runner now defers predictor assembly until all 32 `model_L.pt` files are
  present. A partial bounded calibration therefore succeeds without pretending
  to be a complete predictor.
- The writable workspace is
  `A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829`.
  Layers 1–4 completed there at the same 25,000/rank-256/batch-256/two-epoch
  settings: layer 1 recall 0.8412; layer 2 recall 0.8329; layer 3 recall
  0.8133; layer 4 recall 0.8093. These are calibration values only.
- The next controlled batch completed layers 5–9 in the same workspace:
  layer 5 recall 0.7986; layer 6 recall 0.8082; layer 7 recall 0.8161;
  layer 8 recall 0.8411; layer 9 recall 0.8420. The workspace now contains
  model/checkpoint evidence for layers 0–9, while assembly remains explicitly
  deferred until all 32 layer files are present.
- A further controlled five-layer batch completed layers 10–14. The staged
  workspace therefore now has layers 0–14 of 32. The last recorded layer-14
  recall was 0.8465. The run is intentionally paused at this batch boundary;
  no next batch, predictor assembly, conversion, server, or inference has
  started.

## Safety/result boundary

This is not a complete predictor bundle and must not be converted, registered,
served, or described as a PowerInfer-ready model. It is a timing/quality
calibration for choosing the remaining controlled training schedule. After the
run, `nvidia-smi` showed 30 C, 0% utilization, and 67 MiB used of 16,303 MiB.

## Verification

- PowerShell parser check passed for the edited runner.
- `python local_agent/test_powerinfer_pipeline.py` passed (22 tests) after the
  bounded-training, idempotent-vault, staged-workspace, and deferred-assembly
  controls were added.
- `python tools/powerinfer/test_production_registry.py -v` passed (3 tests).

## Conversion, packaging, and native sparse-runtime acceptance

- After all 32 bounded checkpoints were assembled, the staged candidate was
  converted to F16 PowerInfer GGUF and quantized to Q4. The immutable source
  vault was read only throughout. Candidate artifacts remain only in the
  writable staging area; no Ollama/local-agent registration, server, proxy, or
  render was started.
- The first direct native smoke run generated text but correctly failed the
  sparse acceptance condition: its native binary invoked the unrelated system
  Python and `python -m powerinfer` could not import the matching module. It
  therefore offloaded `0.00 MiB` of FFN weights. The log is retained as failed
  evidence and the candidate was not accepted on that result.
- `run_pipeline.ps1` now scopes `Path` and `PYTHONPATH` only for the native
  child process, putting `external/PowerInfer/.venv/Scripts` first. The caller
  environment is restored in `finally`. This is required because upstream
  native code invokes the literal `python -m powerinfer` while calculating its
  GPU split. Validation records are timestamped, including split flags, so a
  retry does not overwrite a prior attempt.
- The corrected controlled smoke validation passed on 2026-08-30: CUDA
  acceleration and solver invocation were observed, the generated GPU-index
  adapter was applied, and `2322.00 MiB` of FFN weights were offloaded to the
  RTX 5080. The Q4 candidate used `6303.93 MiB` total VRAM and generated a
  coherent continuation. Afterwards the card reported 33 C, 0% utilization,
  and 73 MiB used. Exact evidence: `validation/main_smoke_20260830_175105.log`
  and `validation/split_flags_20260830_175105.json` in the staging workspace.
- This is a smoke acceptance only. A cold/warm multi-turn benchmark and quality
  comparison remain required before the candidate can be marked production-ready
  or exposed through any local-agent route.

## Bounded cold/warm benchmark acceptance

- The first benchmark attempt was stopped after it exposed the same upstream
  literal-Python issue in the server launcher. Only that controlled benchmark's
  Python and loopback server processes were stopped; GPU memory returned to
  baseline immediately. Its log remains retained as diagnostic evidence.
- `record_acceptance_gate.py` now passes the isolated PowerInfer venv through
  to both native child processes. It also timestamps its smoke log, server log,
  and acceptance report; it never overwrites a previous validation run. The
  report was corrected to inspect the packaged `output/activation` directory,
  where the runtime actually requires the 32 activation files. Finally, the
  parser now accepts a cached `.gpuidx` adapter when it offloads a nonzero
  amount of FFN weights; solver invocation is required only on the first cache
  creation, not every subsequent load.
- Final report: `validation/acceptance_gate_20260830_175953.json`. It records
  CUDA acceleration, a valid cached GPU index, `2322.00 MiB` FFN offload, all
  32 activation files, and 20 cold plus 20 warm loopback turns with zero
  request failures. Mean decode rate: cold `110.729` tokens/sec; warm
  `100.743` tokens/sec. The service was bound only to `127.0.0.1` and exited
  after the check; post-run GPU state was 33 C, 0% utilization, 84 MiB used.
- The candidate remains `status: candidate`: no server is left running, and it
  has not been added to Ollama, the model picker, router, or any agent-facing
  endpoint. A human quality review and an explicit promotion decision remain
  separate requirements.

## Quality-review packet prepared (no inference)

- Added `tools/powerinfer/quality_comparison.py` and its three-test offline
  suite. It creates a fixed ten-case, benign comparison packet covering exact
  formatting, JSON, uncertainty, instruction following, planning, and concise
  explanations. It does not start models, connect to endpoints, alter routes,
  or retain project/private prompts.
- A reviewer records baseline and candidate responses plus 0–2 rubric scores,
  then the verifier applies explicit thresholds (default candidate mean >= 1.5
  and no more than 0.25 below the baseline). This makes the separate human
  quality gate reproducible rather than a subjective one-off.
- Prepared, unfilled packet:
  `validation/quality_review_packet.json` in the staged ReluLLaMA candidate.
  It is not evidence of quality and does not promote the model.

## Controlled baseline/candidate quality capture — candidate not promotable

- The operator authorized the next quality step. The current abliterated local
  baseline, `huihui_ai/qwen3-abliterated:8b`, and the ReluLLaMA Q4 candidate
  were run **sequentially**, never concurrently. Each used the same ten benign
  prompts, a deterministic token cap, loopback-only endpoints, and immediate
  release after capture. Both captures completed all ten requests without API
  errors. No ComfyUI, render, proxy, or local-agent route was started.
- The baseline followed the core constrained prompts. The candidate clearly
  failed nine of ten basic cases: it ignored the three-line constraint,
  produced invalid JSON, claimed an unknown file existed, calculated the wrong
  total, echoed instead of summarizing, ignored `READY only`, did not repair
  JSON, expanded a two-step plan into repetition, and did not state the binary
  edit approval boundary. Its short benchmark-style explanation was the one
  plausible pass. This is an objective output review, not a claim that a human
  has approved scores.
- Captures are preserved under
  `local_agent/runtime/powerinfer_quality_reviews/` as
  `quality_baseline_qwen8b_20260830_182222.json` and
  `quality_candidate_relu7b_20260830_182317.json`. The original staged
  validation directory is read-only, so no evidence was overwritten.
- Result: retain `relu-llama-7b` as an isolated candidate; it is not eligible
  for registry acceptance, proxy launch, model-picker exposure, or agent
  routing. Any future retry must first investigate Llama-2 prompt-template and
  instruction-tuning alignment, then repeat the same capture and human review.

## Resumed guarded continuation

- The operator explicitly resumed the remaining calibration. The active
  15–19 batch is followed by `tools/powerinfer/resume_calibration_guarded.ps1`,
  a narrow continuation helper scoped only to absent layers 20–31 in the same
  staged workspace.
- It preserves existing checkpoints, waits for layer 19, uses a <=70 C start
  gate, polls during each one-layer child process, and force-stops that child
  at the 82 C emergency ceiling. It does not launch a PowerInfer server, an
  Ollama model, ComfyUI, or a render.
- The first wrapper attempt exposed a Windows PowerShell 5.1 argument-passing
  incompatibility: it collapsed the Python script path and flags into one
  filename. Layer 20 failed before writing a checkpoint, and the wrapper
  stopped as designed. The wrapper now launches its child through `pwsh.exe`
  (PowerShell 7), retains the same thermal boundary, passed its expanded
  offline test suite (23 tests), and layer 20 was restarted successfully.

## Completed calibration evidence

- The guarded continuation completed layers 20–31 and assembled the staged
  predictor. The staged workspace now contains all 32 `model_L.pt` checkpoints,
  32 per-layer metrics records, an assembled `predictor/` directory, and its
  `HASHES.json` integrity record.
- Read-only metric aggregation recorded recall min/mean/max of
  `0.7986` / `0.8262` / `0.8668`. These are calibration measurements, not an
  inference-quality acceptance result.
- At completion, the RTX 5080 was idle at 30 C, 0% utilization, and 68 MiB
  reported memory use. The guarded continuation process had exited normally.
- Conversion, quantization, model loading, native validation, benchmarking,
  registration, and serving remain unstarted and require a separate explicit
  authorization plus their existing acceptance gates.
