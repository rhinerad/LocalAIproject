# 2026-08-29 — Worker-farm live bounded-sample acceptance

## Live evidence

- Docker Desktop engine recovered after preserving the two affected transient
  runtime directories by renaming them. `docker version` returned server
  version `29.7.2`.
- The loopback-only Redis service was recreated after a health-check-only
  environment correction and reported `healthy` on `127.0.0.1:6379`.
- One dedicated Windows Celery worker started with the `solo` pool and
  `CUDA_VISIBLE_DEVICES=-1`, connected to the authenticated loopback broker,
  and registered only `local_agent.worker_farm.tasks.distill_export`.
- Synthetic job `distill_5090ec5b50892412f0c1a04a` was queued and completed.
  Its worker task returned `review_required`, `candidate_count: 3`, and the
  metadata ledger recorded `result_distill_5090ec5b50892412f0c1a04a`.
- The worker-farm core and Termux gateway contract suites passed 16/16 from the
  repository root after the live sample.

## Boundaries retained

The run handled only the built-in benign synthetic fixture. No actual historical
transcript, private export, raw artifact content, model, GPU operation, render,
Chroma write, or persistent-memory promotion was used. Artifact payloads remain
AES-256-GCM envelopes; only metadata was inspected.

## Follow-up

Any real export requires an explicit operator-selected source and approval. The
next remote-worker step remains the separately gated private-overlay plan.
