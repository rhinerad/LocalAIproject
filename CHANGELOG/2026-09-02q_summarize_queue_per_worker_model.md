# 2026-09-02 — worker farm: summarize queue reads per-worker model, not a fleet-wide constant

## Scope

Follow-up to `2026-09-02o_summarize_embed_farm_queues.md`. That pass wired
`summarize_conversation` straight to `context_compactor.MODEL`
(`llama3.1:8b`) as if every worker would run the same model. It won't:
`mac_worker` is recorded (`worker_farm/README.md`'s "known worker
machines" table) as choosing `krith/mistral-nemo-instruct-2407-abliterated`
instead — a non-safety-tuned model, deliberately, so it won't refuse to
summarize sensitive conversation content the operator already approved for
secondary-machine handling under the `judge_evaluation` trust boundary.
Any future worker may choose a third model again. Fixed the mismatch
before it caused `summarize_conversation` to silently fail against every
non-`llama3.1:8b` worker.

## What changed

`local_agent/context_compactor.py`:
- `_installed()` and `summarize_old_messages()` both gained optional
  `model=`/`host=` (and `timeout=` on the latter) overrides, defaulting to
  the existing workstation constants (`MODEL`, `router.CPU_HOST`, `12`) so
  every existing caller's behavior is unchanged.

`local_agent/worker_farm/tasks.py`:
- `_summarize_messages()` now reads the model from that worker's own
  `FARM_SUMMARIZE_MODEL` environment variable, falling back to
  `context_compactor.MODEL` only if unset. Passes it through to
  `summarize_old_messages(..., model=..., timeout=120)` — the wider
  timeout (vs. the workstation's interactive 12s default) accounts for a
  background farm job on slower CPU-only hardware not racing a live turn.
  The "not installed" result now also reports `model_expected` so a
  missing-model failure names which model was actually checked for.
- `embed_chunks` left untouched — fixed on `nomic-embed-text`, since
  embedding doesn't have the same refusal-risk rationale that motivates
  `mac_worker`'s summarizer choice.

`local_agent/worker_farm/README.md`: corrected the "not yet usable" section
to describe the per-worker `FARM_SUMMARIZE_MODEL` lookup instead of
assuming `llama3.1:8b` fleet-wide, and cross-referenced the "per-worker
model choice" table.

`TODO.md`: swarm-offload item (Phase 2 #5) updated with this change and
its test coverage; blocker line now names `mac_worker`'s actual chosen
model instead of the generic default.

## Tests — written, NOT executed

`local_agent/test_context_compactor.py` (new file, workstation's regular
`local_agent` test environment, not the farm venv):
- `test_model_and_host_and_timeout_overrides_are_honored` — confirms a
  non-default model/host/timeout is passed through to both `_installed`
  and `oll.chat`, using `mac_worker`'s actual recorded model string as the
  test value.
- `test_default_call_unchanged_for_existing_workstation_callers` — signature
  regression guard: default `model` is still `context_compactor.MODEL`,
  default `host` is still `None`, default `timeout` is still `12`.
- Existing three tests (no-model-installed, valid-JSON success path,
  invalid-JSON refusal) untouched and still apply to the default-argument
  path.

**Not run this session** — no shell access. Command for the operator:
```
python -m unittest local_agent.test_context_compactor -v
```
(plain `python`, not the farm venv — this module isn't part of
`worker_farm/`.)

## Why this still isn't "the farm is helping the agent yet"

Unchanged from `2026-09-02o`: no worker has Ollama or any model installed,
so `summarize_conversation` will report `{"summarized": false,
"model_expected": ...}` on `mac_worker` until the operator installs
`krith/mistral-nemo-instruct-2407-abliterated` there and sets
`FARM_SUMMARIZE_MODEL` in that worker's launch environment. No ACL
re-grant, no deployment, no `agent.py` caller — same as before.

## What was not done

No SSH into the Mac, no Ollama install, no `FARM_SUMMARIZE_MODEL` actually
set anywhere, no test execution, no `agent.py` changes.
