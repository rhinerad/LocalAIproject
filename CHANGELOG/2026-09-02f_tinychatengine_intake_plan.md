# 2026-09-02 — TinyChatEngine research + staged intake plan

## Scope

Phase 1 / Task 2 (engine architecture evaluation) continuation. Operator
asked to "research tinyengine and make a plan to try to implement it."
Since the literal `mit-han-lab/tinyengine` project has no desktop/GPU path
(microcontroller-only, confirmed in the prior research pass), this was read
as referring to the sibling project `mit-han-lab/TinyChatEngine`, which does
target x86/ARM/CUDA. That inference is flagged in `TODO.md` rather than
silently assumed, in case it's wrong. Research and planning only — no
clone, no build, no download, no GPU use, consistent with this repo's
GPU-gateway-approval discipline.

## What was done

Read the upstream `mit-han-lab/TinyChatEngine` README in full via the
in-app browser (GitHub's rendered page, not a raw fetch guess). Wrote
`tools/tinychatengine/INTAKE_PLAN_2026-09-02.md`: a staged, gated
implementation plan (Stage 0 research through Stage 7 registry decision),
mirroring the evidence/approval discipline already established for
PowerInfer in this repo (hash-pinned source since TinyChatEngine ships no
tagged releases, no GPU stage without explicit approval, no registry
without a passed human quality gate).

## Key findings recorded

- MIT license.
- **No HTTP server** — CLI chat binary only (`./chat`). An OpenAI-compatible
  proxy wrapper equivalent to `local_agent/powerinfer_openai_proxy.py` does
  not exist and would need to be built before any agent routing integration
  (Stage 7).
- **CUDA backend is real but narrow**: only W4A16 (int4 AWQ) on GPU, and
  only for Llama-2-generation/CodeLlama models in the published model zoo —
  no Llama-3, no Mistral, no VLM (VILA/LLaVA) on CUDA, only on CPU/ARM.
- **Windows CUDA build is upstream-labeled "Experimental,"** requires a
  manual `-arch=sm_xx` Makefile edit. This RTX 5080 is Blackwell (`sm_120`),
  and TinyChatEngine's CUDA kernels predate that architecture (2023 release)
  — compatibility is unverified by upstream and unverified here. Flagged as
  the largest technical risk in the plan.
- No batching/continuous-serving/concurrency support documented — a
  real-time single-session CLI, not a serving stack.
- Project has no tagged releases, 35 open issues / 6 open PRs, one open
  issue as recent as November 2025 — not abandoned, but a research-lab
  project without a release cadence.

## Verification

Findings are sourced directly from the rendered GitHub README (fetched via
the in-app browser after `web_fetch` on raw.githubusercontent.com/github.com
was denied by this session's tooling), not from search-snippet summaries
alone — the earlier search-based pass was treated as preliminary, this pass
as the actual source-read.

## What was not done

No repository clone, no commit hash pinned yet, no build attempted (CPU or
GPU), no model downloaded, no GPU load, no agent code touched. Stage 1 of
the plan (cheap CPU-only build/smoke-test) has not been started — three
explicit open questions are recorded in the plan doc for the operator
before it begins.

## What's still open

Operator sign-off on: (1) whether the CUDA model-coverage gap (no Llama-3/
Mistral on GPU) is worth pursuing given PowerInfer's comparable-generation
sparse candidate already failed its own quality gate; (2) whether to
greenlight Stage 1 now while holding Stage 3 (GPU/`sm_120`) for separate
approval; (3) confirmation that "tinyengine" meant TinyChatEngine, not the
MCU project, since that was inferred rather than stated directly.
