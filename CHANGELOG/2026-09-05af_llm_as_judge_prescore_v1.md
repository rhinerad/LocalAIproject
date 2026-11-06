# 2026-09-05af — LLM-as-judge pre-score v1 (captured runs + CPU sidecar)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05af**.

Task #48. Design: `docs/design_notes/LLM_AS_JUDGE_PRESCORE_2026-09-05.md`
(`CHANGELOG/2026-09-05z`). No live `agent.answer` replay, no GPU, no farm,
no `APP_REVISION` bump.

## What changed

- `operator_eval.score()` stays in-memory and model-free (boolean
  `passed` only).
- New `capture_run()` writes `eval_cases/results/{run_id}.json`
  (`operator-eval-result-v1`) with the captured answer, deterministic
  `passed`, and optional `operator.quality_score` 0–5 (`--quality`).
  Omit the quality key until the operator grades. `quality_score=0` is
  stored.
- `authoritative_score(result)` reads only `operator.quality_score`. A
  judge verdict schema raises `TypeError`. Extra kwargs raise `TypeError`.
- New `judge_eval.py`: CPU `oll.chat` on `router.CPU_HOST`, model
  `llama3.1:8b` (`FARM_SUMMARIZE_MODEL`), `keep_alive="0"`, `num_gpu: 0`,
  `response_format` schema. Sidecar `eval_cases/judge/{run_id}.json`
  with `advisory: true`, `auto_accepted: false`. Never writes `passed`
  or `operator.quality_score`.
- Safeguards: `LOCAL_AGENT_LLM_JUDGE=0`; `judge_control.json` default
  `off` until `judge-enable`; skip when `router.chat_busy()`; circuit
  breaker at `n_paired>=12` (Spearman ρ<0.40 or MAE>1.50 or binary
  disagree>0.40) sets `disabled`; re-enable only with
  `judge-enable --ack-report`, resetting to `untrusted`.
- `operator_eval.py report` plus in-process recompute when a pair
  completes. `parse_ok: false` rows are dropped, not coerced to 0.

## Tests

From `local_agent/`:

```text
python -m unittest test_operator_eval test_judge_eval -q
```

17/17 OK.

Type-isolation: `learning.py`, `exemplar_embeddings.py`,
`worker_farm/judge_rubric.py`, and
`tools/powerinfer/quality_comparison.py` have no `judge_eval` /
`operator-eval-judge-verdict` hits. A deliberate `import judge_eval` in
a temp `learning.py` is detected (`test_isolation_lock_fails_on_deliberate_bad_import`);
asserting that file is clean fails with
`[('learning.py', 2, 'import judge_eval')]`.

## Files

- `local_agent/operator_eval.py`
- `local_agent/judge_eval.py` (new)
- `local_agent/test_operator_eval.py`
- `local_agent/test_judge_eval.py` (new)
- `local_agent/eval_cases/.gitignore` (new)
- `TODO.md`
- `docs/design_notes/LLM_AS_JUDGE_PRESCORE_2026-09-05.md` (status)

## Scope

No live replay. No `--allow-gpu`. No farm/Mac judge. No DeepEval/Ragas.
No GUI. No `outputs/equal_shares/`. GUI not started.
