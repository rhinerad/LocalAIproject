# 2026-09-04f — Farm efficiency evaluation: 4 findings, no code

## Scope

Operator sent a prompt requesting a from-scratch "Farm Swarm Architecture"
spec (Ratchet Loop, Supervisor/Worker over WebSockets/ZeroMQ/FastAPI,
progressive disclosure). Flagged before executing: the Farm already exists
and is live (Celery/Redis/WireGuard, not the transport the prompt assumed)
— this exact wrong assumption was already caught and corrected once, on
2026-09-02. Asked the operator what was actually wanted; answer: evaluate
whether any of the three patterns could make the *existing* farm more
efficient, and estimate effort.

## What was written

`docs/FARM_EFFICIENCY_EVALUATION_2026-09-04.md` — audits each pattern
against the real, current architecture rather than a hypothetical one:

1. **Progressive disclosure — real, unaddressed gap.** `tools.py::schemas()`
   sends full descriptions for all ~65 registered tools every turn,
   filtered only by `PROJECT_ONLY_TOOLS` (no true lazy-load). comfyui-mcp's
   own `--compact` mode (`list_tools`/`describe_tool`/`call_tool`) is a
   working precedent. Medium effort — needs a before/after regression eval
   against `test_native_tool_calling.py`/`test_action_resolver.py` (57+29
   tests) since indirection is a known small-model tool-selection risk.
2. **Ratchet Loop — high effort, high risk, not really a farm item.**
   Confirms the 2026-09-02g correction (autoresearch is an ML-training
   loop, not a harness pattern). Automatic `git revert` on a mechanical
   metric is exactly the class of action `CLAUDE.md` treats as most
   dangerous elsewhere in this project. Not recommended near-term.
3. **Code-execution offload to the farm — no evidence of a bottleneck.**
   `run_code` is already fast/bounded locally; no data shows host CPU
   contention. Don't build without evidence first.
4. **Mac worker `--concurrency=2` — cheap, real, testable.** Not named in
   the operator's original prompt at all; found by re-examining the actual
   farm code (`max-concurrency=1` today, serializing summarize/embed/
   judge/probe). One-line config change, empirically reversible. Flagged
   as the recommended first experiment.

`TODO.md` — three new tickets under the comfyui-mcp section, ordered by the
doc's recommendation (concurrency experiment first, meta-tool layer second,
evidence-gathering for code-execution offload third).

## What was not done

No code changed. No Celery concurrency flag flipped. No meta-tool layer
built. No `run_code` instrumentation added. This is a research/estimation
pass only, per what the operator actually asked for once the original
prompt's stale premise was corrected.
