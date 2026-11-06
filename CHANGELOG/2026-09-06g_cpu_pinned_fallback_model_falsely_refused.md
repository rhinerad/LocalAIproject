# 2026-09-06g — CPU-pinned 8B fallback model falsely refused

Date: 2026-09-06. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-06`: **2026-09-06g**.

Claude session. Live bug reported by the operator: a chat pinned to
`huihui_ai/qwen3-abliterated:8b` on the CPU tier, with the GPU idle,
produced this self-contradictory routed message:

> Selected model huihui_ai/qwen3-abliterated:8b cannot run now: it is not
> installed on the CPU tier and the GPU tier is unavailable or not selected.
> CPU requested; using Huihui 8B on CPU (num_gpu=0, 4 threads). GPU idle (84
> MB used, no foreign compute process) No model is being substituted for
> this pinned chat.

The message asserts the model "cannot run" and then immediately describes
correctly running it — because that is literally what happened internally:
a correct decision was computed and then overwritten by a stale refusal
check, with both halves' text concatenated into one `why` string.

## Root cause

`local_agent/router.py`, `decide()`'s CPU-tier branch (~line 1855-1919).
`_paired_cpu_fallback(model, ...)` resolves against `FALLBACK_REASONING_MODEL`
unconditionally — it ignores its own `model` argument (`del model,
primary_model` on entry) — and correctly finds the pinned 8B model reusable
from the GPU Ollama store with `num_gpu=0`. `selected` gets set to that
resolved model and `why` correctly describes it (`"CPU requested; using
Huihui 8B on CPU..."`).

Several lines later, a final gate (`if model and not on_cpu: if not
paired_cpu_fallback: selected = None; why = "...cannot run now..."`) exists
to stop that same speculative resolution from silently substituting 8B in
for an *unrelated* pinned model (a real, correct behavior — see
`test_gpu_only_pin_refuses_instead_of_substituting_when_busy`, a GPU-only
pin must still be refused, not silently become Huihui 8B). But
`paired_cpu_fallback` is a *different* variable, only set by the
primary-14B-pairing and coding-model branches above it. When the pinned
`model` is itself exactly the fallback model (as in this bug), neither of
those branches ever runs, so `paired_cpu_fallback` stays `None` and this
gate fires — discarding the already-correct `selected` and prepending the
"cannot run now" refusal in front of the text that was already assembled,
producing the contradictory combined message.

## Fix

Changed the final gate's condition from `if not paired_cpu_fallback:` to
`if not paired_cpu_fallback and not _is_configured_variant(model,
FALLBACK_REASONING_MODEL):`. When the pinned model **is** the fallback model
itself, using the GPU-store copy with CPU flags is not a substitution at
all — it's running the exact model that was asked for — so it must not be
refused. Any other pinned model (not itself the fallback, and not
authorized via `paired_cpu_fallback`) is still correctly refused, preserving
the existing anti-silent-substitution behavior.

## Tests

```
python -m unittest local_agent.test_router_switching -v
python -m unittest local_agent.test_native_tool_calling local_agent.test_capability_routing local_agent.test_router_switching local_agent.test_general_assistant local_agent.test_ollama_chat_telemetry
```

New `test_cpu_pinned_fallback_model_not_falsely_refused` reproduces the
exact live shape (model pinned to `FALLBACK_REASONING_MODEL`, present only
in the GPU Ollama store's tags, `prefer="cpu"`, GPU idle) and asserts
`decision.model` stays the fallback model with no "cannot run now" text.
**Confirmed the test actually catches the bug**: reverted the fix in a
scratch copy of `router.py`, re-ran the new test alone, watched it fail
(`decision.model` came back `None`) exactly as the operator reported, then
restored the fix and confirmed it passes again — not just "test added,
assumed to work."

`test_router_switching` 52/54, combined suite 210/212 — the 2 failures are
`test_coding_mode_selects_coding_model_when_gpu_idle` and
`test_unknown_coding_model_falls_back_cleanly`, the same pre-existing,
unrelated coding-model-selection failures already noted in
`2026-09-05ed`/`2026-09-05ee`/`2026-09-06f` (confirmed to fail identically
before this change too; this fix never touches the coding-model branch).
Explicitly re-verified this change does **not** regress
`test_gpu_only_pin_refuses_instead_of_substituting_when_busy` — that's the
scenario the narrower `_is_configured_variant` check (instead of a blanket
"was `selected` already resolved") was written to protect.

## Not changed

- The `paired_cpu_fallback` authorization gate itself, or any coding-model
  logic.
- No GPU work performed. No `outputs/equal_shares/**` touched.

## Files

- `local_agent/router.py`
- `local_agent/test_router_switching.py`
- `CHANGELOG/2026-09-06g_cpu_pinned_fallback_model_falsely_refused.md`
- `TODO.md`
