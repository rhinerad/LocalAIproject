# 10-node Worker Farm — architecture plan (2026-08-29)

## Purpose and boundary

This plan is now active only for the **local CPU-only Phase 1 bootstrap** in
`local_agent/worker_farm/`. It is not authorization to expose a queue, add a
remote worker, start a cluster, run a model, or process private historical
exports. The Ryzen/RTX 5080 workstation remains the only interactive control
plane. A future ten-node Intel cluster (60 CPU cores, 160 GB aggregate RAM,
1 GbE) is a private, asynchronous worker farm. It must never start ComfyUI,
edit workstation files, grant permissions, or make itself an authority over the
control plane.

The current Phase 1 implementation uses loopback-only Redis and a CPU-only
Celery worker with a single allow-listed, review-only sample distillation job.
It stores raw source/result artifacts with authenticated AES-256-GCM and has
no Chroma promotion, rendering, shell execution, model loading, or remote
listener. Its explicit readiness and activation sequence is documented in
`local_agent/worker_farm/README.md`.

Aggregate RAM is not unified memory. A multi-node model uses network transport
between partitions. At 1 GbE, do not make all ten nodes a sequential inference
pipeline. Batch work and use the smallest viable model partition; use remaining
nodes for independent horizontal workloads.

## Proposed minimum stack

| Concern | Planned component | Reason |
|---|---|---|
| Durable ingress/backpressure | RabbitMQ | Publisher confirms, acknowledgements, bounded prefetch, priorities, dead letters. |
| General background work | Celery | Durable retries, fan-out/fan-in, schedules, explicit queue routing. |
| Batched model work | Ray Core / Ray Data | Long-lived model actors and independently parallel micro-batches. |
| Job authority | PostgreSQL | Idempotency keys, leases, state, reviews, provenance. |
| Raw artifacts | MinIO | Immutable source logs, PDFs, exports, outputs and encrypted archives. |
| Retrieval | ChromaDB gateway | One controlled writer, searchable encrypted-at-rest storage, source metadata. |

Messages must contain only a signed task envelope: task ID, artifact URI,
SHA-256, task type, expiration, idempotency key, and policy version. Raw logs,
documents, media, and exports stay in artifact storage.

## Phase A — capacity and trust gates

- Inventory all nodes and measure end-to-end 1-GbE throughput/latency.
- Reserve one CPU core per node for OS/network/monitoring; start with five
  CPU-heavy workers per six-core node.
- Establish private VLAN/LAN rules, TLS/authentication between services, and
  no public queue/model/database endpoints.
- Implement backup/restore and encrypted-artifact tests before production data.
- Benchmark a smaller single-node judge first. A distributed 70B judge is an
  experiment only after RAM, throughput, batch saturation, and recovery tests.

## Phase B — batch fabric

- RabbitMQ queues: judge, researcher fetch/extract/summarize/embed/ingest,
  Teacher, Student, synthetic evaluator, chat-export extraction/distillation,
  encryption, quarantine, and dead letter.
- Use publisher confirms and manual acknowledgement after durable output write.
- Set low prefetch for model workers; higher but bounded prefetch for lightweight
  fetching/parsing work. Set batch windows of 250 ms–2 s and benchmark batches
  of 4/8/16/32.
- Celery handles ordinary durable pipelines. Ray owns long-lived inference
  actors and micro-batch execution. Persist every output outside Ray memory.

## Phase C — four workflows

### 1. Judge evaluation

The workstation sanitizes a completed task log, uploads it to MinIO, and queues
a reference. The cluster batches jobs through a versioned evaluator rubric.
Structured output must cite exact artifact evidence for every criticism. Results
are advisory only; they cannot edit the workstation or change policy. Store raw
results as AES-256-GCM artifacts and promote only approved compact lessons.

### 2. Autonomous Researcher ingestion

Use an operator-maintained allowlist of URLs, PDFs and repositories. Preserve
the original source first, apply robots/rate-limit and private-address checks,
then extract, normalize, summarize, chunk, embed using `nomic-embed-text`,
deduplicate, and submit only through the Chroma gateway. Every chunk retains
URI/commit/page/hash/license/timestamp metadata. Treat source text as data, not
instructions; quarantine prompt injection and malformed material.

### 3. Teacher/Student synthetic data

Use separate Ray pools for Teacher, Student, evaluator and curator roles.
Queue scenario bundles of 8–64 independent examples, not sequential dialogues
across all nodes. Prefer smaller replicated models for throughput; reserve any
large distributed judge for high-value final scoring. Store schema-valid JSONL
with model versions, seed, task, rubric, output, score, and provenance. Human
review is required before training use.

### 4. Historical memory distillation

Preserve incoming ChatGPT/Claude/other exports in encrypted raw storage. Never
embed full noisy transcripts. A deterministic parser and Extractor role create
only candidate preferences, hardware facts, verified project decisions, golden
code exemplars, and uncertain claims. Every candidate has source reference,
date, project scope, confidence and review status. Approved records go to
separate memory collections; uncertain records stay non-retrievable pending
review. Embeddings/search indexes remain technically searchable, so protect
Chroma with encrypted disks/backups, private networking and access control;
encrypt raw source text and sensitive fields rather than embedding ciphertext.

## Mandatory acceptance gates

- Workstation submission returns before any cluster result is available.
- Queue recovery never duplicates encrypted results, Chroma records, or JSONL.
- Worker crash, broker restart, database restart, Chroma failure and encryption
  failure all have tested recovery paths.
- No cluster worker can call workstation control endpoints.
- Every promoted RAG memory and training item has provenance and human approval.
- The 70B judge has measured throughput and a smaller fallback before use.
