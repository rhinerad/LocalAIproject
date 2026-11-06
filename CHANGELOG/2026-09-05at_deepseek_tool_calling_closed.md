# 2026-09-05at — DeepSeek-14B tool-calling avenue closed

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05at**. Follows
`CHANGELOG/2026-09-05n` (R1-tools template) and the operator's
"one more attempt" Part 2. **No `router.py` / `CAP_LOGIC` edits. No new
tag.** Probe: `artifacts/benchmarks/2026-09-05_deepseek_one_more/probe.json`.

## 1. Temperature / num_predict (same case 1 `read_file` prompt)

Tag `deepseek-r1-abliterated-14b:r1-tools`, GPU `:11434`, `think=false`
(agent-like; 2026-09-04r). Full advertised GPU catalog = 67 schemas.

| Setting | native call | Notes |
|---|---|---|
| temp **0.0**, unlimited predict (116 s) | **`see_image`** `{path: local_agent/README.md, action: see_image}` | CoT leaked into `content`; still the wrong tool + invented `action` |
| temp 0.0, **`num_predict=128`** (1.6 s) | **[]** | `done_reason=length`; truncated mid-reasoning toward `see_image` |
| 2026-09-05n hop 2 (temp 0.2, think on) | **`see_image`** | invented `language=python` |

Lowering temperature did not change the tool. Capping `num_predict` made
the hop worse (cut off before any call). Not a sampling-borderline miss.

Control: same temp 0.0 / `think=false` but **only `read_file` in the
schema list** → native `read_file` `{path: local_agent/README.md}`
(correct). So the weights can emit the right call when the catalog is
one tool; with 67 tools they prefer a vision tool for a markdown file.
That is catalog-drowning / reasoning quality, not a format gap. Huihui-14B
already picked `read_file` from the full catalog (2026-09-05b 1a). Shrinking
schemas for DeepSeek would be a DeepSeek-only crutch, not a reason to keep
it on `CAP_LOGIC`.

## 2. Other maintained R1 tool-calling tags

Did **not** pull or retag.

| Tag | Track record | Why not |
|---|---|---|
| `MFDoom/deepseek-r1-tool-calling:14b` | ~79.5k pulls, **1 year stale** | Own readme copies DeepSeek's notice: function calling **unstable**, looped calls or empty responses. Template is JSON `{name, parameters}` in R1 tokens, not a quality upgrade. 9 GB non-abliterated distill. |
| `aleshribar3/deepseek-r1-tool-calling:14b` | ~2.7k pulls, 4 months | Already the template we applied in 2026-09-05n. |
| `ishumilin/deepseek-r1-coder-tools` | ~559k | Cline/agent-coding fork, not a logic/`read_file` specialist. |

No better-maintained 14B R1 tools tag is worth a 9 GB pull on this
evidence.

## 3. Hop 1 silence vs 2026-09-04r

2026-09-05n hop 1: `eval_count=315`, empty `content`, empty `tool_calls`,
thinking stripped into `message.thinking`. That **is** the 2026-09-04r
empty-completion shape (thinking channel ate the turn). Already fixed in
the agent: tool hops send `think=false` and retry once if still empty.

This probe with `think=false` did **not** go silent — it wrote CoT into
`content` and still called `see_image`. Empty-completion is separately
already handled; it is not the remaining DeepSeek bug. The remaining bug
is wrong-tool selection under the live 67-tool surface.

## Recommendation

**Close this avenue.** Do not retag. Do not pull MFDoom. Do not patch
prompts or `CAP_LOGIC` here. Tool-using logic hops should stay a
Huihui-14B operator decision, not another DeepSeek experiment.
