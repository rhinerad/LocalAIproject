# 2026-09-04r — Empty-completion guard + think:false on chat tool hops

Date: 2026-09-04. Host: DuranGamingPC.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04r**
(`2026-09-04o` compact CPU profile, `p` Layer B; this is not a revert of either).

Live chat: `7d474ba55d244abe`. Two desktop turns on CPU Huihui 8B
(`ctx` 16384) completed HTTP 200 after generating 838 then 637 tokens,
and `agent.answer()` stored `""`. Distinct from the 2026-09-04o
`OllamaUnavailable` / 8B-eviction miss. Compact schemas / Layer A were
not the filter; do not change them in this PR.

## What shipped

- `ollama_client.chat_stream(..., think=None)`: agent CPU/chat tool hops
  pass `think=False` (same reason `measure_ollama_kv_cache` already does).
  PowerInfer hops still omit it. When `message.thinking` has length and
  visible content is empty with no tool_calls, stderr logs
  `empty visible content after N thinking char(s)`.
- Hop loop: if a hop ends with no tool_calls and no stripped reply, retry
  **once** with think disabled (`skip_farm` on the retry decide). If still
  empty, return a visible "model returned no text" sentence — never `""`.
  Farm `{content:"", tool_calls:[]}` is no longer treated as a successful
  farm hop.
- Compact CPU schemas and Layer A/B untouched.

## Tests

Before this PR: 76 + 46.

```
python local_agent/test_native_tool_calling.py -q
  Ran 80 tests
  OK

python local_agent/test_action_resolver.py -q
  Ran 46 tests
  OK
```

Existing 76 native-tool assertions held. Four new tests: `chat_stream`
sends `think:false`; logs 200 thinking chars when content is empty;
thinking-only stream through `agent.answer()` retries then returns text
(never `""`); compact-CPU + non-matching `"how far along are you in the
comfyui job?"` returns `_EMPTY_COMPLETION_REPLY` after one retry.

## Not this PR

11435 dying in GPU discovery despite `CUDA_VISIBLE_DEVICES=-1` (why turn
1 fell through to 11434 and attempted a GPU load while `:8188` was up,
HTTP 499). Tracked in `TODO.md` as its own ops ticket. Layer A regex
tightening only if 8B still skips `call_tool` after `think:false` ships.
