# 2026-09-05ee — `_VisibleTextFilter` "prefix" state no longer buffers pure whitespace forever

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05ee**.

Third sibling of `2026-09-05ec` and `2026-09-05ed` — same failure family
("the model produced nothing this turn" on a 14-beat/~30-image
Bulma/Android 18 prompt run on `huihui_ai/qwen3-abliterated:14b`), a third
distinct shape, this time in a different branch of the same
`_VisibleTextFilter` class `ed` had just fixed.

## The bug

`_VisibleTextFilter` (`local_agent/ollama_client.py`) buffers a small
leading amount of streamed text in its `"prefix"` state so a partial
`<think>`/`</think>` marker isn't mistaken for prose and released early.
The hold condition was:

```python
leading = self.pending.lstrip()
if self.OPEN.startswith(leading) or self.CLOSE.startswith(leading):
    return ""
```

If everything fed so far is whitespace, `leading` (the lstripped buffer)
is `""`. `"<think>".startswith("")` and `"</think>".startswith("")` are
both trivially `True` in Python — every string is a prefix-match of the
empty string. So when the model's `content` stream is pure whitespace
tokens, `leading` stays `""` forever, the condition is permanently true,
and the filter holds every whitespace token in `self.pending` and never
transitions state, for the entire generation. Unlike the `"hidden"` state
(capped defensively: `self.pending = self.pending[-len(self.CLOSE):]`),
the `"prefix"` state had no such cap, so `self.pending` grew without limit
and nothing was ever released.

This is a **worse** blind spot than `ed`'s shape: because state never
reaches `"hidden"`, `ed`'s new `unclosed_hidden_chars()` (which only
fires when `state == "hidden"`) never sees it either. A turn hitting this
exact path telemetered `visible_chars=0`, `thinking_chars=0`, **and**
`unclosed_think_chars=0` — mechanically identical to a truly silent model,
with zero trace that ~4 seconds of real generation happened.

## Live reproduction

Confirmed on `huihui_ai/qwen3-abliterated:14b`, a `capability=image`
request classified against the same oversized 14-beat/~30-image
Bulma/Android 18 prompt (~17,582 prompt tokens, tool catalog + multi-image
ask) as `ec`/`ed`: Ollama's own telemetry reported `eval_count=275`
(~4.1s eval — real generation, not a truncated request) whose entire
streamed `content` was whitespace. Direct repro against the pre-fix
filter:

```python
import ollama_client as oc
f = oc._VisibleTextFilter()
out = []
for i in range(275):
    piece = f.feed('\n' if i % 2 == 0 else ' ')
    if piece:
        out.append(piece)
print(out)            # [] -- nothing ever released
print(f.state)         # "prefix" -- never left prefix state
print(len(f.pending))  # 275 -- grew unbounded
```

Confirmed against the **fixed** code (same script):

```
num flushes: 267
total chars flushed: 275
state: visible
pending len: 0
unclosed_hidden_chars: 0
```

All 275 whitespace chars are eventually released, `state` correctly
resolves to `"visible"` instead of sitting stuck in `"prefix"`, and
`pending` never exceeds a small bound at any point along the way.

## What changed

`local_agent/ollama_client.py`, `_VisibleTextFilter.feed()`, `"prefix"`
branch only:

- The `startswith` hold check now only runs `if leading and (...)` — it no
  longer treats an empty `leading` as evidence of a forming tag.
- A new `if not leading:` branch handles the whitespace-only case
  explicitly: both markers (`<think>`, `</think>`) are entirely
  non-whitespace, so whitespace can never grow into one. Once
  `len(self.pending)` exceeds `max(len(OPEN), len(CLOSE))` (8 chars) with
  `leading` still empty, no tag is coming — the filter gives up, flushes
  everything held so far as ordinary visible text, and transitions to
  `"visible"` (mirroring the existing plain-prose fallback rather than
  adding a new code path). Below that bound it still returns `""` and
  waits, same as before, so a few genuine leading newlines/spaces ahead of
  a real tag or real prose are unaffected.
- The non-empty-`leading` logic (partial-tag matching, full
  `<think>`/`</think>` detection at position 0, leaked-preamble handling
  via `find`) is untouched — restructured only to skip cleanly past the
  new whitespace branch, not rewritten.

Whitespace released this way flushes as ordinary visible content — it is
not reasoning, so there is no hidden-reasoning-leak risk in surfacing it.
No new telemetry field was added for this path; the fix is that the hold
terminates, not that it needs a new counter (per scope: nice-to-have, not
required, and the existing `unclosed_think_chars`/`thinking_chars`
telemetry from `ed` already correctly reports 0 for this shape since no
tag was ever seen).

## Not changed

- `_is_degenerate_completion` (`ec`'s 112-blank-numbered-item shape) —
  untouched, different failure shape (all-visible-blank, not
  all-whitespace-buffered).
- `unclosed_hidden_chars()` / `StreamEnd.unclosed_think_chars` (`ed`'s
  unclosed-`<think>`-in-content shape) — untouched; a `<think>` that opens
  and never closes still goes through the `"hidden"` branch exactly as
  `ed` left it (see regression test below).
- No `router.py`, capability-routing, or demotion logic touched.
- No GPU work, no live render, no `outputs/equal_shares/**` touched.

## Tests

```
python -m unittest local_agent.test_ollama_chat_telemetry -v
python -m unittest local_agent.test_native_tool_calling local_agent.test_ollama_context_options local_agent.test_measure_ollama_kv_cache local_agent.test_capability_routing local_agent.test_agent_tracing -v
python -m unittest local_agent.test_router_switching -v
```

`test_ollama_chat_telemetry`: 15/15 passed (10 pre-existing + 5 new).
Second command: 147/147 passed. New/changed cases (all in
`test_ollama_chat_telemetry.py`):

- `test_visible_text_filter_pure_whitespace_never_vanishes` — the exact
  275-alternating-`\n`/` ` repro above, run directly against
  `_VisibleTextFilter`: asserts some output is released, all 275 chars
  eventually flush, and `state` ends at `"visible"` with `pending` empty
  and `unclosed_hidden_chars() == 0`.
- `test_visible_text_filter_prose_from_first_token_unaffected` — ordinary
  prose starting immediately still streams through unchanged.
- `test_visible_text_filter_prose_after_leading_whitespace_unaffected` — a
  few leading newlines/spaces then real prose still releases the whole
  buffered text together, unchanged.
- `test_visible_text_filter_think_block_with_leading_whitespace_unaffected`
  — leading whitespace, then a full `<think>...</think>` block, then
  prose in the same and later chunks: no leak, no regression, close-tag
  detection at a non-zero offset still works.
- `test_visible_text_filter_think_from_first_token_still_hidden` — a
  `<think>` that opens immediately and never closes still enters and stays
  in `"hidden"` with `unclosed_hidden_chars() > 0` — confirms the
  whitespace-flush path cannot intercept a genuine tag prefix.

`test_router_switching`:
`RouterSwitchingTests.test_coding_mode_selects_coding_model_when_gpu_idle`
and `.test_unknown_coding_model_falls_back_cleanly` still fail on this
tree, identically to what `ed` reported (pre-existing
router.py/coding-model-selection failures, confirmed unrelated — this
patch never touches `router.py` and both failures are about coding-model
tier/name selection, nothing to do with `_VisibleTextFilter`). Not claimed
as fixed or newly broken here. No other test in any suite run changed
status.

## Files

- `local_agent/ollama_client.py`
- `local_agent/test_ollama_chat_telemetry.py`
- `CHANGELOG/2026-09-05ee_whitespace_prefix_swallow_fix.md`
- `TODO.md`
