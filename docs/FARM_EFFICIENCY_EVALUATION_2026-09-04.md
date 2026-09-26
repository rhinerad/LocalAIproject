# Farm efficiency evaluation — 2026-09-04

## Why this doc exists

Operator asked whether three architectural patterns (Karpathy's
`autoresearch` "Ratchet Loop," a Supervisor/Worker offload pattern, and
"Progressive Disclosure" tool-schema design) could make the existing worker
farm more efficient, and how hard each would be. This is **not** a
from-scratch architecture spec — the Farm already exists and is live
(Celery + Redis + WireGuard, cut over to WSL Ubuntu Docker CE on
2026-09-03, not ZeroMQ/FastAPI/WebSockets — see `docs/ARCHITECTURE.md`).
This doc audits each pattern against what's real today and estimates effort
for whatever's actually worth building. Read-only research; no code
changed by this doc.

## Finding 1 — Progressive disclosure: real gap, worth fixing, medium effort

`local_agent/tools.py::schemas()` (line ~2679) sends the full JSON schema
for **every** registered tool into the system prompt on every turn, gated
only by `PROJECT_ONLY_TOOLS` (which hides Equal Shares-specific tools from
general chats — a much coarser filter than true lazy-loading). As of today
the registry is **~65 tools**. Several descriptions are long by design
(they carry usage warnings, not just a signature) —
`render_story_image`/`plan_story_image` and `schedule_phone_messages` are
each roughly 800–1500 characters of description alone, before the JSON
schema wrapper. This is unconditional per-turn overhead, worst for
whichever model has the tightest context window — `context_compactor` caps
its own CPU-model calls at `num_ctx=4096`, and the Mac worker's
summarization model is a similarly-sized local model, both far tighter than
the host's Qwen 14B.

This is a genuine instance of the pattern the operator named — not
something `HARNESS_OPTIMIZATION.md` already closed. That audit found
context *compaction* and concurrency-safe execution already built; it did
not specifically measure tool-schema token cost.

**comfyui-mcp itself ships a working precedent** worth studying directly
rather than designing from scratch: its `--compact` /
`COMFYUI_MCP_TOOL_MODE=compact` mode collapses its ~41 tools into 3
meta-tools (`list_tools` → `describe_tool` → `call_tool`), explicitly
documented as "the right trade for small local models." That's the same
shape this project would need.

**Effort estimate: medium, a few days, not a quick win.** The mechanical
part (wrap `TOOLS` behind `list_tools`/`describe_tool`/`call_tool`) is
small. The real cost is proving it doesn't *regress* tool selection —
indirection is known to hurt small-model tool-calling accuracy, which is
exactly the failure mode this project already spent real effort guarding
against (`action_resolver.py`'s deterministic pre-classification exists
specifically because free-form tool selection by a small model is
unreliable). This needs a real before/after eval against the existing
`test_native_tool_calling.py` and `test_action_resolver.py` suites (currently
57 + 29 tests), not just a mechanical refactor — and probably a bounded
allowlist (offer the meta-tool layer only to the farm/CPU-model path, keep
the host's larger model on direct schemas) rather than a blanket swap.
**Ticket-sized. Do not attempt as a drive-by change.**

### Finding 1, sharpened — model-aware harness profiles (operator idea, 2026-09-04)

Operator's own framing, worth recording verbatim in spirit: when routing
sends a turn to a CPU-served model, the harness should be *aware* of that
and adapt — not just trim the tool schema, but give that model a whole
different, simpler instruction/tool profile than the GPU model gets, then
switch back when routing returns to GPU. That's a generalization of
Finding 1 above into a first-class concept (a "harness profile" tied to
`router.py`'s existing CPU/GPU host decision) rather than one flat
schema-trimming rule.

This isn't a new pattern for this codebase, it's two existing ones
combined:

- `action_resolver.py` already exists because free-form tool selection by
  a small model is unreliable — it deterministically pre-resolves certain
  requests into `(tool_name, args)` before the model drafts anything, for
  exactly the cases a weaker model can't be trusted to reason through
  itself.
- `context_compactor.py` already varies its own call parameters
  (`num_ctx`, `num_thread`, `num_gpu:0`, timeout) by which model/host is
  serving a given call.

A **CPU profile** would combine both ideas deliberately: the reduced
meta-tool/allowlisted tool set from the base Finding 1 proposal, leaning
harder on `action_resolver`-style deterministic pre-resolution instead of
trusting the small model's free-form tool choice, and shorter, more
directive rule-based instructions instead of the same verbose prompt built
for the host's 14B model. A **GPU profile** stays as today: full schema,
full free-form multi-hop loop. The switch trigger is whatever `router.py`
(or `farm_offload.should_route()`, once the dynamic model-routing work
lands) already decides about which model/host is serving the turn — this
doesn't need a new signal, it needs the harness to *read* a signal that
already exists and branch on it.

**Effort estimate: same medium/ticket-sized bucket as Finding 1, slightly
larger scope** — it's Finding 1's meta-tool work plus an explicit
profile-switch point in the harness plus wiring `action_resolver` in more
aggressively for the CPU path, still needing the same before/after
tool-selection regression eval. Sequencing matters: doesn't make sense to
build this before Finding 1's meta-tool layer exists, since the CPU profile
*is* the meta-tool layer with `action_resolver` bias added on top, not a
separate system.

## Finding 2 — Ratchet Loop (autoresearch-style test-and-revert): high effort, high risk, not really a "farm efficiency" item

Already researched and correctly scoped on 2026-09-02
(`CHANGELOG/2026-09-02g_autoresearch_resource_note.md`): `autoresearch` is
an autonomous ML-training-experiment loop (edits `train.py`, bounded runs,
keeps changes that improve a metric), not a general context/tool harness.
The mechanical shape — isolated execution, a strict metric, automatic
revert on regression — is real and reusable, but applying it here means
building new automation, not making the existing farm faster. Two
concrete candidate applications already flagged, neither farm-throughput
related: PowerInfer predictor/calibration tuning, or a future Supervisor
Loop pattern.

**Effort estimate: high, and the risk profile is the real blocker, not the
code.** Automatic `git revert` on a mechanical test failure is exactly the
class of action `CLAUDE.md` treats as maximally dangerous elsewhere in this
project ("Never delete raw attempts, approved references... a denied
destructive command is a signal to choose a non-destructive route"). Any
real implementation needs the loop confined to an isolated worktree/branch
that can never touch the working tree the operator is looking at, plus a
mechanical metric trustworthy enough to gate an automatic revert without
human review — neither exists today. **Not recommended as a near-term farm
efficiency item.** Worth a separate, explicit go/no-go conversation if
PowerInfer calibration tuning specifically becomes a priority again.

## Finding 3 — Offloading code execution/sandboxing to the farm: likely not worth it, needs evidence first

`run_code` already runs in a fast local sandbox (CPU-only, 30s timeout,
120s cap, no project-tree access) on the host. Routing it to the Mac
worker over WireGuard would add real network round-trip latency for
something that's already bounded and fast — the farm's actual efficiency
win so far (summarize/embed offload) works because those tasks are slow
enough (18.5s–55s+ on the Mac) that offloading them frees the host for
other work; `run_code` doesn't have that profile. **No evidence exists
today that host CPU contention from `run_code` is an actual bottleneck** —
without that evidence this would be optimizing something that isn't slow,
at the cost of adding latency and a new failure mode (farm-down fallback)
to a tool that currently has neither. **Not recommended unless someone can
show `run_code` calls are actually contending with host inference for
CPU.** **Update 2026-09-04m:** that evidence was gathered; there is no
real contention. Ticket closed as not worth building. See the follow-up
at the bottom of this doc.

## Finding 4 — a real, cheap-to-test farm win the original prompt didn't name

The Mac worker's Celery instance runs at `max-concurrency=1` — every
`summarize`/`embed`/`judge`/`probe` job is fully serialized, even though
`embed_chunks` is now capped at 8 chunks per call (yesterday's live-bug
fix) and typically finishes in ~13s. On a backlog (e.g. a cold embedding
cache needing many 8-chunk batches), throughput is bounded by that
serialization, not by per-call latency. Raising concurrency to 2 is a
one-line Celery worker flag, not a redesign.

**Effort estimate: low — an afternoon, not a project.** The risk is purely
empirical: the Mac is a 2019 Intel Core i9 laptop already running Ollama
for `summarize` concurrently with `embed_chunks`; two concurrent jobs might
thrash rather than help. This is directly testable — bump
`--concurrency=2`, replay a batch of queued embed jobs, compare wall-clock
throughput against today's serialized baseline, revert if it's worse or if
thermal/latency degrades. **Recommended as the actual near-term "make the
farm more efficient" experiment** — it's cheap, reversible, and measurable,
unlike the other three.

## Summary / recommendation

| Idea | Real farm efficiency win? | Effort | Recommendation |
|---|---|---|---|
| Progressive disclosure (meta-tool schema layer) | Yes, real and unaddressed | Medium (days, needs a tool-selection regression eval) | Worth doing as its own ticket, not a quick patch |
| Ratchet Loop / auto-revert | Not really a farm item | High + real safety risk | Defer; separate decision if PowerInfer tuning specifically comes up |
| Code-execution offload to farm | No — measured 2026-09-04m | N/A | **Don't build.** Forced overlap slowdown 2%; real sessions don't overlap |
| Mac worker `--concurrency=2` | Yes, directly testable | Low (an afternoon) | Do this first — cheapest, fastest signal |

Three tickets added to `TODO.md` Phase 2 for the two worth pursuing plus
the evidence-gathering step for the third.

**2026-09-04l follow-up (scoping only):** Finding 1 / ticket 2 now has a
concrete design at `docs/HARNESS_PROFILES_DESIGN_2026-09-04.md` and a
clean before-baseline of **65/65** `test_native_tool_calling.py` +
**29/29** `test_action_resolver.py` (this doc's 57+29 count was stale).
Live registry is 67 tools, not ~65. No harness code in that pass.

**2026-09-04m follow-up (ticket 3 measured, closed):** Finding 3's
recommendation stands and is no longer blocked on missing evidence.
`run_code` does **not** contend with host inference in a way that would
justify a farm offload. Details:
`CHANGELOG/2026-09-04m_run_code_cpu_contention_not_worth_building.md`,
raw numbers in
`artifacts/benchmarks/run_code_cpu_contention_2026-09-04.json`.
No offload path was designed or written.
