# 2026-09-05z — LLM-as-judge pre-score: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05z**.

Task #48. Design note only — no Ollama call, no `operator_eval.py`
behavior change, no `APP_REVISION` bump.

Doc: `docs/design_notes/LLM_AS_JUDGE_PRESCORE_2026-09-05.md`.

## Finding

`operator_eval.py` is still the 2026-08-24 intake: `pending` → `approved`
→ a boolean `score()` over required/forbidden tools and phrases. That
function prints JSON and **does not write** the `eval_cases/results/`
directory it already mkdir's. There is no operator 0–5 quality field, so
the correlation §4b asked for cannot be computed against anything that
exists today.

The CPU helper to copy is `context_compactor.summarize_old_messages`
(`llama3.1:8b` on `router.CPU_HOST`, `keep_alive="0"`, `num_gpu: 0`,
`response_format` schema, return `None` on failure). Farm
`judge_transcript` is a different thing (regex over saved chats,
`review_required`).

v1: persist captured runs + operator `--quality 0-5`; judge sidecar
`eval_cases/judge/{run_id}.json` (`score` 0–5, closed `flags`,
`advisory: true`); `report` CLI; **circuit breaker** that sets
`judge_control.json` to `disabled` when Spearman/MAE/binary-disagree
miss thresholds at `n>=12`, so an uncorrelated judge stops being
called. Judge never writes `passed`. Live `agent.answer` replay is not
v1 (mutating tools + GPU).

No production code changed.
