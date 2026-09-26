# Upgrade 22 — Loop Engineering for the local agent

## Intent and source

This upgrade is the operator-approved design response to Addy Osmani's
[“Loop Engineering”](https://addyosmani.com/blog/loop-engineering/) (June 7,
2026). Its useful pattern is not “let an agent do anything forever.” It is a
durable control loop that discovers work, plans it, executes only allowed
actions, verifies results independently, records state, and stops at a
machine-checkable condition or an operator gate.

The local agent already has pieces of the foundation:

- native structured tool calls plus server-side validation;
- durable task checkpoints and bounded observations (`agentic_state.py`);
- source-labelled project retrieval;
- explicit feedback and operator evaluation cases;
- persistent memory, GPU gateway, render preflight, remote identity rules, and
  append-only audits.

It does **not** yet have a single loop controller, a formal triage queue, or an
independent completion verifier. Those are the missing pieces.

## Non-negotiable boundaries

- A loop never starts, resumes, or cancels a ComfyUI/Equal Shares render.
- A loop never downloads a model, dataset, package, or external asset.
- A loop never edits protected evidence, deletes/moves raw data, grants a phone
  capability, changes GPU policy, or changes a security rule.
- A loop may only run actions already allowed by `tools.py`; schemas are hints,
  never authority.
- It cannot mark itself complete. Completion requires deterministic checks and,
  when appropriate, a separately instructed verifier.
- Every run must preserve a bounded, redacted audit record and stop on a token,
  time, tool-hop, or failure budget.

## Target loop

```text
explicit operator goal
  -> durable goal record and measurable stop condition
  -> scheduled discovery / triage
  -> bounded plan for one safe next step
  -> whitelisted action or proposed change
  -> deterministic verification
  -> independent verifier reviews evidence, not hidden reasoning
  -> update state: complete | next step | blocked | needs operator
```

The controller should use `local_agent/runtime/loop_engineering/` for state:

- `goals/<id>.json` — goal, scope, stop condition, budgets, approval level;
- `triage.jsonl` — discovered candidates and why they were accepted/rejected;
- `runs/<id>.jsonl` — action, tool result fingerprint, verification result;
- `review_queue.json` — items requiring operator attention;
- `LOOP_STATUS.md` — compact human-readable current state.

Raw chats, unredacted paths, secrets, and arbitrary model output do not enter
these files. Existing privacy-preserving feedback rules still apply.

## Phased plan

### Phase 0 — design and baseline

- [x] Save the operator's Loop Engineering goal in persistent memory.
- [x] Record the source and safety constraints in this design document.
- [x] Define 20 golden loop scenarios: maintenance, file inspection,
  documentation drift, regression repair, blocked render request, and remote
  denial. Include expected stop states.
- [x] Establish an initial metrics harness for task completion, false completion,
  unnecessary actions, tool failure recovery, runtime, and token cost.
- [x] Add an explicit `loop_enabled` setting defaulting to false.

### Phase 1 — read-only maintenance loop

- [x] Implement a stdlib-only `loop_controller.py` that accepts only an
  operator-created goal with a machine-checkable stopping condition.
- [x] Add read-only discovery adapters for test results, the upgrade board,
  changelog freshness, and stale task checkpoints.
- [x] Run at most one candidate per scheduled turn; create a review item for
  ambiguity, missing evidence, a failed check, or any state-changing action.
- [x] Reuse current heartbeat automation only for discovery/triage; do not start
  a second watcher or duplicate an active owner.
- [x] Add deterministic tests for budgets, idempotent resume, duplicate-run
  refusal, scope isolation, and redacted audit output.

### Current baseline evidence

- `local_agent/evaluations/loop_golden_scenarios.json` contains 20 distinct
  reviewable safety and maintenance scenarios; `loop_evaluation.py` verifies
  their contract without calling a model.
- `loop_metrics.py` computes only recorded controller facts. With no enabled
  production loop runs, completion/pass-rate/runtime values are empty rather
  than invented, false-completion rate is explicitly unmeasured, and model
  token cost is zero by design.
- `loop_verifiers.py` is a separate bounded evidence registry. It makes no
  completion decision and cannot execute commands, contact services, or call a
  model; its output is compact facts suitable for a later independent review.

### Phase 2 — guarded repair proposals

- [x] Permit an explicitly requested, failed-check loop to inspect a text file
  and produce a unified diff through the
  existing proposal path, never write a project file directly.
- [x] Require the ordinary sidebar approval for every exact file edit,
  including configuration files.
- [x] Re-run the named targeted test after an approved edit; record the result
  before considering the next step.
- [x] Block self-retry after two identical failures; create a review item
  instead of looping.

### Phase 3 — independent evidence verification

- [x] Build a deterministic verifier registry first: file hashes, JSON-shape
  checks, and recorded-result predicates. Service health and arbitrary command
  execution remain out of scope for this first registry.
- [x] Add an optional separate-model verifier only after the deterministic
  registry is measured. It receives the goal, diff fingerprint, test output,
  and evidence, not the implementer's hidden reasoning. It is CPU-only,
  disabled unless explicitly requested, and returns `needs_operator` on any
  malformed/unavailable result.
- [x] Require agreement between deterministic checks and the verifier for a
  consequential completion claim; disagreement becomes `needs_operator`.
  The agreement helper is a policy result, not an authorization or self-issued
  completion claim.
- [ ] Measure false-positive and false-negative completion decisions against
  the golden scenarios with an explicitly approved live CPU-model run.

### Phase 4 — isolated multi-agent work

- [ ] Use worktrees only after the target workspace is a functioning Git
  repository and the operator explicitly enables parallel work.
- [ ] Assign one role to inspect/implement and another to review/verify; never
  allow simultaneous edits in the same checkout.
- [ ] Keep GPU/render/model-load authority centralized in the existing gateway.
- [ ] Require human review before merging any worktree change into the working
  project.

## First useful loops

1. **Regression triage:** run existing non-rendering tests, group failures by
   stable signature, open one evidence-backed repair proposal.
2. **Documentation drift:** detect changed interfaces without matching README,
   changelog, or test updates; create a review item rather than auto-editing.
3. **Task resumption:** resume one explicit, unblocked operator goal from its
   checkpoint, perform one safe next action, then stop if verification is not
   conclusive.
4. **Model/tool reliability evaluation:** replay approved golden tool-call
   traces against a selected local model and publish metrics. This informs any
   future LoRA decision without changing production behavior.

## Explicit non-goals

- No recursive self-modifying code.
- No autonomous training, LoRA creation, model selection, or model download.
- No unattended ComfyUI work, media queue draining, or GPU load.
- No “done” claim based solely on the same model's self-assessment.
