# 2026-09-02 — judge_evaluation: first real worker-farm workflow

## Scope

The operator's stated objective for the worker farm: make the local agent
"better, more efficient, smarter, faster and more logical," keep workers
continuously busy, and scale as more machines join — with the explicit
requirement that the work actually helps the agent, not busywork.

Of the four workflows in `docs/WORKER_FARM_ARCHITECTURE_PLAN_2026-08-29.md`,
Judge evaluation is the one most directly tied to that goal: it turns the
operator's own repeated bug reports this session (unverified completion
claims, work dumped back on the operator, ComfyUI/H3 leakage, unexecuted
direct requests) into a mechanical, continuously-running sweep over real
conversation history, rather than waiting for the operator to notice and
report each instance manually.

## Explicit operator decision on data scope (record for the trust boundary)

Real chat transcripts under `local_agent/chats/` are private operator data
and include sensitive/NSFW content (confirmed directly — an actual sampled
transcript contained an explicit image-generation prompt, and a separate
transcript showed the agent iteratively drafting NSFW-leaning "calibration
categories" for a model-uncensoring task at the operator's request). The
worker-farm design has, until now, deliberately restricted secondary
machines to public/non-sensitive data only (see `worker_farm/README.md`'s
policy table and `Add-Phase1SecondaryWorkerCredential.ps1`'s refusal to
grant the `distill` queue).

Asked explicitly and directly, twice — once about real transcripts in
general, once specifically after being shown that NSFW content is actually
present in the corpus — the operator confirmed: **send everything to
secondary machines, no filtering.** This is recorded here as a deliberate,
informed widening of the existing trust boundary, the same way `distill`
queue access would require its own explicit decision. It is not an inferred
default and should not be treated as one for any future workflow.

## What was built

- **`local_agent/worker_farm/judge_rubric.py`** — pure, dependency-free
  pattern matching over a saved chat's `messages` list. No model call, no
  GPU, no network access. Four rules:
  - `unverified_completion_claim` — assistant text claims an action
    happened ("I've fixed...", "this has been created...").
  - `possible_work_dumped_on_operator` — assistant text tells the operator
    to go do something manually ("you'll need to...", "please open...").
  - `specialist_project_leak` — assistant mentions ComfyUI/H3/Equal
    Shares-specific terms when the preceding user turn didn't invoke that
    project (the same failure class fixed twice already this session, now
    swept continuously instead of found by accident).
  - `direct_action_request_not_executed` — a user message reads as a direct
    action request, and the following assistant turn reads like
    instructions rather than a performed action.
  Every finding is `review_required`, never a proven conclusion — documented
  limitation: saved chat JSON has no per-turn tool-result field, so this is
  a coarser net than agent.py's own live checks.
- **`local_agent/worker_farm/tasks.py`** — new `judge_transcript` Celery
  task, queue `judge`. Deliberately simpler than `distill_export`: the
  transcript travels in the envelope and the findings come back as the
  plain task result, reusing the queue's own WireGuard-tunnel +
  scoped-Redis-ACL protection rather than adding a second
  encrypted-artifact-store layer — consistent with the operator's own
  explicit choice above, and avoiding over-engineering relative to what was
  actually approved.
- **`local_agent/worker_farm/celery_app.py`** — routes
  `judge_transcript` to the `judge` queue.
- **`local_agent/worker_farm/submit_judge_batch.py`** — scans
  `local_agent/chats/*.json`, queues any chat that's new or changed since it
  was last queued (tracked in a small local ledger,
  `worker_farm/runtime/judge_ledger.json`), skips unchanged ones. Meant to
  be re-run repeatedly (cron/scheduled task) so the queue keeps refilling as
  real usage accumulates — the "always stay busy, scales with more
  machines" property the operator asked for, without inventing synthetic
  busywork.

## Verification

```
python -m py_compile local_agent/worker_farm/judge_rubric.py \
  local_agent/worker_farm/tasks.py local_agent/worker_farm/celery_app.py \
  local_agent/worker_farm/submit_judge_batch.py
→ clean

python -m unittest local_agent.worker_farm.test_judge_rubric -v
→ 10 tests, OK

python -m unittest local_agent.worker_farm.test_farm_core \
  local_agent.worker_farm.test_termux_powerinfer2_edge_worker \
  local_agent.worker_farm.test_judge_rubric -v
→ 32 tests, OK (3 skipped — module-level app is None in-process without
  FARM_BROKER_URL set at import time, same documented pattern as the
  existing distill/probe tests; the subprocess registration test is the one
  that proves real registration)
```

Smoke-tested against 8 real files in `local_agent/chats/`: sane, bounded
output — 3 of 8 flagged `specialist_project_leak` (including the transcript
noted above, correctly caught by mentioning ComfyUI/H3-adjacent terms
without the user's turn having invoked that project), 5 had no findings. Not
noisy, not silent.

## What was not done

No job was actually submitted to a live broker (no Redis running in this
verification pass). No worker machine processed a real judge job yet. No
ACL credential change was made — `Add-Phase1SecondaryWorkerCredential.ps1`
already supports arbitrary queue names other than `distill` unmodified, so
granting the `judge` queue to `mac_worker` (or any future machine) is just
`-Queues judge` (or `-Queues probe,judge`) on the existing script; that run
itself is left to the operator/workstation session, not done here. No
finding was auto-applied as a fix to anything — every result is advisory,
same as `distill_export`'s `review_required` pattern.

## What's still open

- Actually grant the `judge` queue and run `submit_judge_batch.py` against
  the live broker, then verify a real judge task completes end to end (same
  proof pattern already used for `connectivity_probe`).
- The rubric is deliberately mechanical/pattern-based, not an LLM judge —
  it will miss semantic failures (bad reasoning, wrong-but-plausible-sounding
  answers, weak inference on vague requests) that only a model reading the
  whole exchange could catch. A future LLM-based judge pass is the natural
  next step, but requires deciding whether secondary machines get their own
  Ollama install or call back to the workstation's — not decided here.
- No re-judging-on-rubric-change mechanism yet: the ledger only tracks
  "chat changed," not "rubric changed." Bumping the rubric later should
  probably force a full re-sweep; not implemented.
