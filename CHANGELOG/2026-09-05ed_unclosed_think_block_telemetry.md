# 2026-09-05ed — Unclosed `<think>` block in `message.content` no longer discards a real completion invisibly

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py --date 2026-09-05`: **2026-09-05ed**.

Diagnosed via `local_agent/knowledge/traces.db`, conversation id
`e40fa885d6134050` (today). Sibling of `2026-09-05ec` and `2026-09-05eb` —
a third distinct failure shape behind the same symptom family ("the model
produced nothing this turn"), this time in `ollama_client.py` itself
rather than in `router.py` capability/demotion logic.

## The bug

`_VisibleTextFilter` (`local_agent/ollama_client.py`) suppresses a leading
`<think>…</think>` block from Ollama's streamed `message.content` so
reasoning never leaks into the visible reply. If `<think>` opens and
`</think>` never arrives before the stream ends, the filter's state stays
`"hidden"` forever and it yields **nothing** — not one visible char — for
the whole turn. Separately, `chat_stream`'s `thinking_chars` counter only
ever incremented from Ollama's native `message.thinking` field, never from
`<think>` text embedded in `content`.

The live trigger: `huihui_ai/qwen3-abliterated:14b` on a `capability=image`
turn with a ~17,578-token prompt (large tool catalog + a 14-beat multi-image
story-image request). The model's chat template ignored the `think=False`
API flag entirely, opened `<think>` inside `content` anyway, and exhausted
its response budget while still inside the block —
`eval_count=275`, ~4.3s eval time, a real, non-empty completion. The turn's
stored telemetry was `visible_chars=0 thinking_chars=0 tool_call_count=0`:
mechanically identical to a truly silent model, with zero trace of the
generation that actually happened. `agent.py`'s generic empty-completion
path (`_is_degenerate_completion`, `_EMPTY_COMPLETION_REPLY`) retried once,
failed identically (same template behavior), and told the operator "the
model returned no text" — true, but useless: the actionable fact (the turn
was too large/complex for the model to finish reasoning about) was
discarded along with the buffered text.

## What changed

`local_agent/ollama_client.py`:

1. `_VisibleTextFilter` gained a `hidden_chars` running counter (incremented
   whenever `feed()` processes text while `state == "hidden"`, including the
   post-tag remainder on the transition call) and
   `unclosed_hidden_chars()`, which returns that counter **only** while
   `state` is still `"hidden"` — it returns 0 the instant a `</think>` is
   actually seen, so a normal, correctly-closed think block is completely
   unaffected.
2. `StreamEnd` gained an `unclosed_think_chars` field (default 0).
3. `chat_stream` computes `visible_filter.unclosed_hidden_chars()` at both
   places it can end a turn — the cooperative-stop early return and the
   normal `done=True`/exhausted-iterator path — and folds it into
   `thinking_chars` before the existing
   `if thinking_chars and not visible_chars and not accumulated_calls:
   _log_empty_thinking(...)` check, so that check now actually fires for
   this shape (previously `thinking_chars` stayed 0 here, so the condition
   never tripped). `_log_empty_thinking` takes an `unclosed_think_chars`
   kwarg and names the unclosed-block shape explicitly in its stderr
   breadcrumb when it's nonzero. The raw reasoning text itself is still
   never surfaced — only the fact and the count.

`local_agent/agent.py`:

4. The `reason_span` for `ollama.chat_stream` now also records
   `unclosed_think_chars` alongside the existing `thinking_chars` /
   `visible_chars`, so it lands in `traces.db` per-turn.
5. `stream_end` is now reset to `None` once per hop (before the
   farm/backend branch), not only inside the `for attempt` retry loop —
   a farm-handled hop skips that loop entirely (`range(0)`), which could
   otherwise leak a previous hop's `StreamEnd` into this hop's diagnosis
   or raise `NameError` on hop 0.
6. When the empty-completion retry is exhausted and the final `StreamEnd`
   has `unclosed_think_chars > 0`, the operator reply is now
   `_UNCLOSED_THINK_EMPTY_COMPLETION_REPLY` — it says the model spent the
   whole turn reasoning and never got to an answer despite generating real
   text, and suggests a smaller/simpler request — instead of the generic
   `_EMPTY_COMPLETION_REPLY` ("returned no text... retry or pick a
   different model"), which reads like the model is broken or silent when
   it isn't.

## Not changed

- The raw buffered reasoning text is still discarded, never returned to the
  caller or the operator — only its length and the fact that it happened.
- `_is_degenerate_completion` (the 112-blank-numbered-item shape from `ec`)
  is untouched; this is a different failure shape (all-hidden, not
  all-numbered-blank-visible).
- No `router.py`, capability-routing, or demotion logic touched.
- No GPU work, no live render, no `outputs/equal_shares/**` touched.

## Tests

```
python -m unittest local_agent.test_ollama_chat_telemetry -q
python -m unittest local_agent.test_native_tool_calling -q
python -m unittest local_agent.test_ollama_context_options local_agent.test_measure_ollama_kv_cache local_agent.test_capability_routing local_agent.test_agent_tracing -q
```

10/10, 98/98, 157/157 (combined last three + native + telemetry = 157)
passed. New/changed cases:

- `_VisibleTextFilter`/`chat_stream` fed a `<think>` that never closes:
  `visible_chars=0`, `thinking_chars > 0`, `unclosed_think_chars > 0` and
  equal to `thinking_chars`, `_log_empty_thinking` called once with
  `unclosed_think_chars` set (`test_chat_stream_unclosed_think_block_is_not_silently_dropped`).
- Same, on the cooperative-stop path
  (`test_chat_stream_unclosed_think_on_cooperative_stop`).
- A normal `<think>...</think>` followed by real prose: `unclosed_think_chars`
  stays 0, `thinking_chars` stays 0, visible prose streams through
  unchanged, `_log_empty_thinking` **not** called — no regression
  (`test_chat_stream_closed_think_block_unaffected_no_regression`).
- `agent.answer()` end-to-end: a hop whose `StreamEnd` carries
  `unclosed_think_chars=640` produces
  `_UNCLOSED_THINK_EMPTY_COMPLETION_REPLY`, not the generic
  `_EMPTY_COMPLETION_REPLY`, and emits a note naming the unclosed-block
  shape with the char count
  (`test_unclosed_think_empty_completion_gets_specific_operator_message`).
- Pre-existing `test_chat_stream_logs_thinking_length_when_content_empty`
  updated for `_log_empty_thinking`'s new `unclosed_think_chars=0` kwarg
  (native `message.thinking` case, no `<think>` in content — this kwarg is
  0 there, confirming the two code paths are additive, not conflated).

`test_router_switching.RouterSwitchingTests.test_coding_mode_selects_coding_model_when_gpu_idle`
and `.test_unknown_coding_model_falls_back_cleanly` fail on this tree
**before and after** this change (confirmed by running
`test_router_switching` alone, isolated, unchanged) — unrelated
pre-existing router.py/coding-model-selection failures, not touched by
this fix (this patch never edits `router.py`). Not claimed as fixed here.

## Files

- `local_agent/ollama_client.py`
- `local_agent/agent.py`
- `local_agent/test_ollama_chat_telemetry.py`
- `local_agent/test_native_tool_calling.py`
- `CHANGELOG/2026-09-05ed_unclosed_think_block_telemetry.md`
- `TODO.md`
