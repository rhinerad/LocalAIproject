# 2026-09-04o — Model-aware harness profiles v1 (compact CPU/farm meta-tools)

Date: 2026-09-04. Host: DuranGamingPC. Mac: Louises-MBP.
Id from `python scripts/next_changelog_id.py --date 2026-09-04`: **2026-09-04o**
(`2026-09-04l` was scoping; `m`/`n` were other farm tickets).
Design: `docs/HARNESS_PROFILES_DESIGN_2026-09-04.md` (approved, three
defaults confirmed).

## What shipped

- `tools.profile_for(Decision)` keys off existing `tier` / `backend`.
  `tier=gpu` → full 67-tool schema. `tier=cpu` or `backend`/`tier=farm` →
  three virtual meta-tools (`list_tools` / `describe_tool` / `call_tool`).
  Meta-tools are **not** in `TOOLS`. Default `schemas()` is unchanged.
- `agent.answer()` recomputes the advertised schema **per hop** after
  `decide()` and after farm-fallback / 14B→8B GPU OOM fallback.
- `call_tool` unwraps in plan-building and again in `run_one()` so
  specialist / batch / `__conversation_id` guards see the inner name.
  Direct real-name dispatch still works.
- CPU hops swap `msgs[0]` to a short compact prompt. Layer A pulls the
  execution-first sentence forward on CPU action requests. No new
  `action_resolver` intents.
- Live Qwythos burned hops on `list_tools(category="file_operations")`
  returning empty; added `_CATEGORY_ALIASES` (`file_operations` → `file`).

`CORE_DIRECT_TOOLS` is documented in `tools.py` as the v1.1 rollback
allowlist and is not advertised.

## Tests

Before this PR (2026-09-04l): 65 + 29.
After, existing assertions preserved; counts grew only by new tests:

```
python local_agent/test_native_tool_calling.py -v
  Ran 76 tests in 7.011s
  OK

python local_agent/test_action_resolver.py -q
  Ran 29 tests in 0.177s
  OK
```

New spies (design §8.3): GPU Decision still sends all 67 tools;
CPU/farm send exactly the three meta-tools; `call_tool` unwraps to
`tools.call`; protected-file and specialist guards see the inner name;
OOM GPU-8B fallback stays on the full schema.

`test_multiple_calls_one_hop_and_named_results` already asserted
`len(tools)==len(TOOLS)` while `_Route` defaulted to `tier=cpu`. That
fixture is now explicitly `tier="gpu"` so the assertion still means
"full registry goes out" rather than silently flipping to compact.

## Live verify (compact Qwythos)

Script/receipt:
`artifacts/benchmarks/2026-09-04m_compact_qwythos_live.py` /
`artifacts/benchmarks/2026-09-04m_compact_qwythos_live.json`
(filename kept from the run; this changelog is `o`).

Prompt: list files in `local_agent` via tools. Farm reachable. Comfy
:8188 was listening (`gpu_busy` true) — farm path is the correct one.

| Check | Result |
|---|---|
| `decide("auto")` | `tier=farm` `backend=farm` `profile=cpu` Qwythos |
| Schema sent to Qwythos | `["list_tools","describe_tool","call_tool"]` |
| Qwythos tool call | `call_tool` `{name: list_dir, args: {path: local_agent}}` |
| Inner execution | `tools.call("list_dir", {path: local_agent})` returned the real `local_agent/` listing (`agent.py`, `tools.py`, …) |

The turn then continued extra hops (wrong `file_operations` category,
then a later farm `None`) and died on hop-after-success:
`OllamaUnavailable` because skip_farm + :8188 busy + Huihui 8B eviction
from `127.0.0.1:11434` timed out. Compact wiring is live-verified; that
final-prose miss is the existing GPU-busy CPU-handoff fail-closed, not a
schema bug. Wall 589.6 s. No 14B load (VRAM stayed ~2.5 GB).

## Not done

Layer B extra CPU-only resolver intents (second PR after this live turn).
`CORE_DIRECT_TOOLS` not advertised. Mac `--concurrency=2` is a different
ticket (`2026-09-04n`, reverted).
