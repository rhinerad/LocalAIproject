# 2026-09-05dm — Mac Celery worker now registers judge_transcript_semantic

Date: 2026-09-05 ~18:38 ET. Hosts: DuranGamingPC and Louises-MBP
(`10.90.90.2`). Id from `python scripts/next_changelog_id.py --date
2026-09-05`: **2026-09-05dm**.

Follow-up to `2026-09-05bo` (task shipped default-off on the
workstation tree) and the leftover noted in `2026-09-05bw` /
`2026-09-05dh`: the live Mac worker had never been restarted against
code that actually contained the task.

## Why kickstart alone was not enough

`farm_health --json` at **2026-09-05T22:37:05Z**, worker
`celery@Louises-MBP`, launchd pid **36469** / `runs=9`:

**Before (registered_tasks):**

- `local_agent.worker_farm.tasks.connectivity_probe`
- `local_agent.worker_farm.tasks.distill_export`
- `local_agent.worker_farm.tasks.embed_chunks`
- `local_agent.worker_farm.tasks.judge_transcript`
- `local_agent.worker_farm.tasks.qwythos_evaluate`
- `local_agent.worker_farm.tasks.summarize_conversation`

No `judge_transcript_semantic`. Mac
`/Users/rhineduran/worker_farm/local_agent/worker_farm/tasks.py` was
still **Sep 5 10:16** (12421 bytes, keep-alive era); `celery_app.py`
**Sep 4 14:59**. `grep -c judge_transcript_semantic` on both files
was **0**. Missing entirely: `semantic_judge.py`, `judge_eval.py`,
`operator_eval.py`. Restarting that process would have re-registered
the same six names.

Did **not** touch farm `.env`, Redis ACLs, or any other farm config.
Mac `.env` mtime stayed **Sep 4 15:38**. `LOCAL_AGENT_LLM_JUDGE` is
not present in that file. No `judge_semantic_control.json` was
created (durable control still defaults to `status: "off"`).

## What was copied (Python only)

scp from the workstation tree onto
`/Users/rhineduran/worker_farm/local_agent/` (LaunchDaemon cwd),
same path as `2026-09-04k`:

| File | Why |
|---|---|
| `worker_farm/tasks.py` | `@app.task` for `judge_transcript_semantic` |
| `worker_farm/celery_app.py` | `task_routes` entry on the existing `judge` queue |
| `worker_farm/semantic_judge.py` | lazy-imported by the new task **and** by `judge_transcript`'s follow-up enqueue; omitting it would ImportError a live mechanical judge |
| `judge_eval.py` | imported by `semantic_judge` at run time |
| `operator_eval.py` | imported by `semantic_judge` / `judge_eval` at run time |

Did not replace Mac `router.py` / `ollama_client.py` / `atomic_io.py`
(already present). Did not enqueue a judge job. Did not run
`python -m local_agent.worker_farm.semantic_judge enable`.

## Restart

`sudo -n launchctl kickstart` needed a password. Non-sudo
`launchctl kickstart -k system/com.local-agent.celery-worker`
succeeded (job `username = rhineduran`).

- launchd pid **36469** → **54698**, `runs` 9 → **10**, `state=running`
- stderr: `Connected to redis://mac_worker:**@10.90.90.1:6379/0` then
  `celery@Louises-MBP ready.` at 18:37:46 ET
- stdout `[tasks]` banner includes `judge_transcript_semantic`

## After — farm_health at 2026-09-05T22:38:05Z

`status: ok`, `workers_responding: true`, `workers:
["celery@Louises-MBP"]`, `missing_expected_tasks: []`.

**After (registered_tasks):**

- `local_agent.worker_farm.tasks.connectivity_probe`
- `local_agent.worker_farm.tasks.distill_export`
- `local_agent.worker_farm.tasks.embed_chunks`
- `local_agent.worker_farm.tasks.judge_transcript`
- `local_agent.worker_farm.tasks.judge_transcript_semantic`  ← new
- `local_agent.worker_farm.tasks.qwythos_evaluate`
- `local_agent.worker_farm.tasks.summarize_conversation`

Existing `qwythos_evaluate` / `summarize_conversation` / `embed_chunks`
/ `judge_transcript` still present. Semantic judge remains default-off
via durable control (`off` when no control file) plus the existing
`LOCAL_AGENT_LLM_JUDGE` kill switch (unset on the Mac; not written).

No workstation source change. No GPU work. No live chat judged.
