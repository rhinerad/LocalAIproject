# 2026-09-02 — HARNESS_OPTIMIZATION.md written (deferred deliverable, now unblocked)

## Scope

The original harness-optimization request (context compaction middleware +
supervisor loop for background offload) from earlier this session, held
per operator instruction pending Phase 1 closure. Phase 1 closed earlier
today (stay on Ollama/current models). Documentation only.

## Research correction

The original request named "OpenHarness (RoboCFO / Minimal Harnesses)" and
"Revfactory" as sources to review. Verified before citing: `OpenHarness`
(`HKUDS/OpenHarness`) and `Revfactory` (`revfactory/harness`) are both real,
findable open-source projects and were used as sources. **"RoboCFO" could
not be verified** — no matching project was found under that name after a
direct search. Rather than invent details about it, `HARNESS_OPTIMIZATION.md`
says so explicitly and relies on OpenHarness plus general 2026 literature on
progressive tool disclosure instead.

## Audit finding — the headline result

Most of what the original request asked for **already exists in this
codebase, working and mostly tested**: reactive threshold-based context
compaction (`context_compactor.py` + `agent.py::_trim_context`, Pillar 1),
progressive/scoped tool disclosure (`PROJECT_ONLY_TOOLS`), parallel
concurrency-safe tool execution, bounded coordinator/worker fan-out
(`dispatch_subtasks`), and — critically — a **live, tested supervisor/
fan-out system** for background work (`local_agent/worker_farm/`,
Celery/Redis over WireGuard, `mac_worker` connected and verified this
session). The gap is narrower than "build this": it's "the farm exists but
doesn't yet route the specific task types (summarization, embedding
generation) the original request named."

One correction found during audit: the sliding-window summarizer's
proposed fixed "6,000 token" threshold is actually inferior to what's
already built — the real trigger (`prompt_tokens > num_ctx`) is tied to
the model's actual adaptive context budget, not a guessed constant.

## What was written

`HARNESS_OPTIMIZATION.md` (project root): research, an audit table mapping
every originally-requested capability to its actual status here, a
two-item real gap analysis (farm task routing; a Letta-style
agent-editable working-context block, flagged as optional/not urgent), a
proposal to extend the existing farm with `summarize`/`embed` queues plus
an in-process eligibility classifier (not a new daemon), and pseudo-code
for the Reason→Act→Observe loop annotated to show it's a description of
the *real* current loop with one new branch, not a rewrite.

`TODO.md`: item 2 (sliding-window summarizer) marked resolved/already-built,
no code needed. Item 5 (swarm offload) updated from "blocked" to
"spec written, not implemented" with the concrete `summarize`/`embed` queue
proposal.

## What was not done

No code written — no new Celery queues, no classifier, no `agent.py`
changes, no `operating_memory.py` extension. `LLMOPS_AUDIT.md` (structured
tracing/observability, the other deferred deliverable from this session)
remains unwritten — separate scope, not addressed here.
