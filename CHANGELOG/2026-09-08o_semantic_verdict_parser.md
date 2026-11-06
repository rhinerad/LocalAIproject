# 2026-09-08 — Semantic verdict parser hardening

- The exact VLM gate now recovers one balanced JSON object when a model wraps a
  response in brief prose, while retaining strict schema and exact-model checks.
- Semantic failure records now include the joined validator reasons, making
  runtime/parser failures diagnosable instead of appearing blank.
- Targeted semantic QA tests remain green (3/3). Production stays gated until a
  structured semantic pass is recorded.
