# 2026-09-04p — Harness profiles Layer B: CPU-only action_resolver intents

Date: 2026-09-04. Host: DuranGamingPC. Mac: Louises-MBP.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04p**.
Parent: `docs/HARNESS_PROFILES_DESIGN_2026-09-04.md` §6.2; v1 live compact
turn `CHANGELOG/2026-09-04o_harness_profiles_v1.md`.

## What was asked

Add CPU/farm-only resolver intents for compact-path failure modes worth
covering after one live compact turn. Start with the design candidates
(`web_search`, `capabilities`, `list_memory`) plus whatever the
2026-09-04o Qwythos extra hops/dead-end showed was missing. Same
discipline as the original five: pattern constant, priority-ordered
classify branch, regression test per intent. GPU free-form unchanged.
`test_action_resolver.py` 29/29 existing must hold; grow only by new
tests. Live-verify one compact-profile turn that exercises a new intent.

## What shipped

- `action_resolver.classify(..., profile="gpu"|"cpu")`. Default `"gpu"`
  is the previous five intents only.
- CPU extras, after the five, still None on ambiguity:
  1. relative `list_dir` — bare folder after the global alias/abs-path
     miss. This is the 2026-09-04o hole: Qwythos burned hops on
     `list_tools(category="file_operations")` then `search=ls` before
     `call_tool(list_dir, {path: local_agent})`, then died on
     hop-after-success eviction. `_PATH_RE` rejects un-rooted names.
  2. `web_search` — explicit "search the web / look up / google", query
     required, no URL (URLs stay `fetch_url`).
  3. `capabilities` — "what can you see/hear/transcribe" / "what tools
     do you have". Does not match the bare word "capabilities".
  4. `list_memory` — "what do you remember" / "list remembered facts".
- Not added (design forbid): `write_file`, `run_code`,
  `start_batch_render`, `render_story_image`.
- `agent.answer()`: global five still classify before `decide()`. On a
  miss, hop-0 `decide(ensure_gpu_evicted=True)` supplies
  `tools.profile_for()`; CPU/farm re-classifies. That Decision is reused
  on hop 0 unless `gpu_gate` changes prefer (farm-fallback still
  re-decides `skip_farm=True`).

## Tests

Before this PR: 76 + 29. After, existing assertions preserved; resolver
count grew only by new tests:

```
python local_agent/test_action_resolver.py -v
  Ran 46 tests in 2.428s
  OK

python local_agent/test_native_tool_calling.py -q
  Ran 76 tests in 10.161s
  OK
```

29 existing resolver tests held. 17 new: classify unit + GPU-none per
intent, query/URL negatives for web_search, CPU greeting still None,
safety stop still wins on `profile="cpu"`, four CPU `agent.answer()`
integrations (model must not run), GPU web_search still uses the model.

## Live verify (compact farm, new relative list_dir intent)

Script/receipt:
`artifacts/benchmarks/2026-09-04p_cpu_resolver_intents_live.py` /
`artifacts/benchmarks/2026-09-04p_cpu_resolver_intents_live.json`

Same prompt as 2026-09-04o: list files in `local_agent`. Farm reachable.

| Check | Result |
|---|---|
| `decide("auto")` | `tier=farm` `backend=farm` `profile=cpu` Qwythos |
| GPU `classify()` | `None` (free-form unchanged) |
| CPU `classify()` | `list_dir` `{path: local_agent}` |
| `tools.call` | `list_dir` only; listing includes `action_resolver.py` |
| Qwythos / `chat_stream` | not called |
| Wall | 4.305 s (v1 compact discovery turn was 589.6 s) |

No GPU 14B load. No hop-after-success eviction. Compact profile
short-circuited the model, which is the Layer B point.

## Not done

`CORE_DIRECT_TOOLS` still rollback-only, not advertised. No new
destructive regexes. Mac `--concurrency=2` remains the reverted
`2026-09-04n` ticket.
