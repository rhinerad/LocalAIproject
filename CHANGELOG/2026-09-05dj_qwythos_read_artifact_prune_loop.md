# 2026-09-05dj — Qwythos hop-limit empty answer is a prune/read_artifact loop, not a 9B-only quirk

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dj**. Diagnosis of
the 2026-09-05de farm live turn (`farm_direct.json`). **No
`router.py` / `agent.py` / tools change this pass.** No extra farm
turns (receipt is enough).

## What the receipt actually did

Prompt: first markdown heading in `local_agent/README.md` (same as
2026-09-05b case 1a). Unpinned → Mac Qwythos. Wall 645 s. Final
`reply=""`. Note: `reached the 6-hop limit; returning current answer`.

| Hop | Tool | Args | Result the *GUI* saw | What the *model* got in context |
|---|---|---|---|---|
| 0 | `list_tools` | `{search:"read"}` | catalog including `read_file` and `read_artifact` | same (small) |
| 1 | `read_file` | `{path: local_agent/README.md}` | full-ish text starting `# Local Agent — …` (`total` later stored as **12188** chars) | **pruned pointer** `artifact_6a735cb16dacc46d` — SSE `tool_result` is pre-prune |
| 2 | `read_artifact` | `{artifact_id: artifact_6a735cb16dacc46d}` (no offset/length) | JSON slice offset 0 length **4000**, `kind=tool:read_file`, `more_remaining` implied | **pruned again** → `artifact_65b406e4609deb09` |
| 3 | `read_artifact` | `{artifact_id: artifact_65b406e4609deb09}` | JSON whose `text` is the **previous JSON**, `kind=tool:read_artifact`, 4304 chars | pruned → `artifact_9d08e185d3382452` |
| 4 | `read_artifact` | `{artifact_id: artifact_9d08e185d3382452}` | one more nesting of the same slice | pruned → `artifact_d61e3f31ab7138ed` |
| — | farm unavailable note | — | CPU Huihui-8B fallback mid-turn | — |
| 5 | `read_artifact` | `{artifact_id: artifact_d61e3f31ab7138ed}` | deeper nesting | pruned |
| 6 | (none) | hop limit | empty prose | — |

The model never indicated it had the heading. It never paged with
`offset` / `next_offset`. Each `read_artifact` used a **new** id copied
from the latest prune pointer. Repeated-failure guard cannot fire:
calls succeed, arguments differ.

SSE `tool_result` for hop 1 still shows the heading because `emit` is
the raw tool string. `artifacts.prune_large_text` runs only when that
string is written into `msgs` (`agent.py` ~2426). The 9B never saw the
heading in its window.

## Root cause (harness, deterministic)

Not “Qwythos mishandles README text.” Not a missing per-tool
satisfaction predicate in the hop loop. The hop loop already asks
“if you have everything, answer in prose”; the model never had the
file in context.

Two numbers close a loop:

- Context budget: `context_prefetch.BUDGETS.tool_result_chars` = **2400**.
  Over that, `prune_large_text` **replaces the entire result** with a
  pointer (no head kept).
- `read_artifact` default `length=4000` (cap 8000) and returns
  `json.dumps({…, "text": chunk, …}, indent=2)`. A 4000-char slice is
  **~4196** JSON chars (measured this session). Always `> 2400`.

So the tool that exists to *undo* prune is itself pruned. The next hop
reads the new artifact, which is the previous JSON, still ~4200 chars,
pruned again. Matryoshka until `MAX_TOOL_HOPS=6`. Empty answer because
every hop after `read_file` was another tool call.

`read_artifact`'s own docstring says paging is deliberate so the model
knows how much it has seen. That only works if the slice **stays** in
the transcript.

## Why Huihui case 1a “worked” without this loop

Farm compact advertises `read_artifact` (`list_tools` found it).
2026-09-05bn Huihui-14B case 1a `gpu_core` did **not** (`read_file`,
`list_dir`, `run_code`, `fetch_url`, `web_search`, `capabilities`).
Huihui called `read_file` `{max_chars:12000}` once and answered
**`"Local Agent README"`** — wrong vs the real first heading
`# Local Agent — a local ChatGPT Desktop equivalent`. That is the
all-or-nothing prune plus no recovery tool: the 14B guessed from the
path. Qwythos followed the pointer instead of guessing, then hit the
loop. 9B behavior is the more faithful reading of the advertised
protocol; the protocol is broken.

## Proposed fix (not applied)

Simple, safe, clearly correct — **do not prune `read_artifact` results**
(skip `prune_large_text` when `name == "read_artifact"`, or prune with
a limit ≥ max encoded slice). That tool is the escape hatch; pruning it
is a closed loop. Tests: default 4000-char slice JSON must remain in
the next hop’s `role=tool` content; a second `read_artifact` must use
`next_offset`, not a new wrapper id.

Optional follow-ups (larger, not required to stop this incident):

- Keep a **prefix** in `prune_large_text` (first `limit` chars + pointer)
  so “first heading” questions can answer without paging.
- Lower default `read_artifact` length so even a pruned JSON would fit
  — fragile vs `indent=2` metadata; worse than skip-prune.
- Hop-loop “same file recovered once → stop paging” — model-policy, not
  a substitute for putting the slice in context.

Do **not** change `CAP_LOGIC` / farm routing for this. Do not add a
Qwythos-only prompt. Do not treat hop-limit as the product answer.

No GPU/farm load this pass.
