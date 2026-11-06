# 2026-08-29 — Deferred Worker Farm roadmap

## Added

- A planning-only ten-node background Worker Farm roadmap in `TODO.md` and
  `docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md`.
- The record covers private RabbitMQ/Celery/Ray batching, a batch-only judge,
  researcher ingestion, Teacher/Student synthetic data, and source-traceable
  historical chat-export distillation.

## Safety boundary

- No cluster services, downloads, model loads, network listeners, external
  accounts, rendering, or local-agent authority changes were started.
- The plan explicitly keeps the workstation as the control plane, treats
  1-GbE multi-node large-model inference as an experiment, and requires
  encrypted raw artifacts, a controlled Chroma writer, provenance, and human
  review before memory/training promotion.
