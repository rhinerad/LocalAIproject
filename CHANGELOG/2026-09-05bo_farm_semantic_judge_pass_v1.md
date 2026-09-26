# 2026-09-05bo — Farm semantic judge pass v1 (advisory, default off)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05bo**.

Task #59. Design: `docs/design_notes/FARM_SEMANTIC_JUDGE_PASS_2026-09-05.md`
(`CHANGELOG/2026-09-05bg`). No live Ollama call, no real chat judged,
`judge_rubric.py` unchanged, no `APP_REVISION` bump.

## What shipped

- `local_agent/worker_farm/semantic_judge.py` — Qwythos-9B on
  `FARM_OLLAMA_HOST` default `127.0.0.1:11434`, `num_gpu: 0`,
  `num_thread: 4`, `num_ctx: 8192`, `keep_alive: 30m`, `temperature: 0`.
  Flags: `judge_eval.FLAGS` plus `bad_reasoning`,
  `weak_inference_on_vague_request`, `plausible_wrong_answer`. Score 0–5.
  Sidecar `farm-judge-semantic-verdict-v1` with `advisory: true`,
  `auto_accepted: false`. Reuses `judge_eval` kill switch
  (`LOCAL_AGENT_LLM_JUDGE`), `_int_score` / `_clean_reasoning` /
  `_metrics` / `_apply_breaker` / `spearman_rho`.
- Celery `local_agent.worker_farm.tasks.judge_transcript_semantic` on
  the existing `judge` queue. `judge_transcript` still returns only the
  mechanical rubric dict; if the semantic pass is enabled it enqueues
  the follow-up and swallows enqueue errors.
- Enable CLI: `python -m local_agent.worker_farm.semantic_judge enable`
  (durable control starts `off`; disabled breaker needs `--ack-report`).
- `operator_eval.authoritative_score` TypeError on this schema too.

## Four safeguards (tested, not comments)

1. **Type isolation.** Isolation grep on `learning.py`,
   `exemplar_embeddings.py`, `judge_rubric.py`,
   `quality_comparison.py`. Adversarial deliberate `import semantic_judge`
   is detected. `authoritative_score` rejects the farm verdict schema.
2. **Kill switch.** Default control `off` skips `oll.chat`.
   `LOCAL_AGENT_LLM_JUDGE=0` skips even when enabled.
3. **Circuit breaker.** 12 paired grades with judge 0 vs operator 5
   → `disabled`; enable without ack raises; ack resets to `untrusted`.
4. **Busy-skip / no write into the subject.** Non-Qwythos resident model
   skips the call. Sidecar does not mutate mechanical status or a
   synthetic chats/ file. Follow-up enqueue failure leaves mechanical
   dict unchanged.

## Tests

Farm venv, repo root:

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_semantic_judge local_agent.worker_farm.test_judge_rubric local_agent.test_operator_eval local_agent.test_judge_eval local_agent.worker_farm.test_farm_core.FarmCoreTests.test_worker_app_registers_the_judge_transcript_semantic_task -q
```

39/39 OK. Fixtures only (`synth_clean` / `what is 2+2?`). No
`local_agent/chats/` read.

## Files

- `local_agent/worker_farm/semantic_judge.py` (new)
- `local_agent/worker_farm/test_semantic_judge.py` (new)
- `local_agent/worker_farm/tasks.py`
- `local_agent/worker_farm/celery_app.py`
- `local_agent/worker_farm/test_farm_core.py`
- `local_agent/operator_eval.py`
- `local_agent/test_operator_eval.py`
- `docs/design_notes/FARM_SEMANTIC_JUDGE_PASS_2026-09-05.md` (status)
- `TODO.md`
