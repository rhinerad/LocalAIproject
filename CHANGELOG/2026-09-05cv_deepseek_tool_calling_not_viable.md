# 2026-09-05cv — DeepSeek tool-calling: not a Coder-style parser gap; close as not viable

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cv**. Gut-check for
the still-open DeepSeek half of
`TODO.md` (native tool-calling template fix). **No `router.py` /
`CAP_LOGIC` / tag / parser change.** Coder half stays closed via
`parse_content_json_tool` (2026-09-05t/u).

Follows `2026-09-05g`, `2026-09-05n`, `2026-09-05t`, `2026-09-05at`.
This ticket exists because the later TODO copy still said “DeepSeek
half still open” after 2026-09-05at closed the live-probe avenue.

## What is still broken after the 2026-09-05n retag

Two tags, two different remaining bugs. Neither is the Coder format gap.

**Production `CAP_LOGIC` tag (unchanged):**
`huihui_ai/deepseek-r1-abliterated:14b-qwen-distill-q4_K_M`.
`ollama show --modelfile` still has **no** `.Tools` / `.ToolCalls` /
`role=tool` branch (reconfirmed this session). Ollama advertises
`capabilities: tools` from the GGUF Jinja, but the live Go template is
DeepSeek-R1 chat only. The model never sees a function-calling
protocol. Symptom in 2026-09-05g: invented README contents,
`inner_tools_executed: []`.

**Experimental retag (not promoted, old tag kept):**
`deepseek-r1-abliterated-14b:r1-tools` (`70cf39bd428e`, same weights,
aleshribar3-style `.Tools` template — reconfirmed `.Tools` and
`.ToolCalls` present). Native `tool_calls` became *possible*:

| Probe | Native | What happened |
|---|---|---|
| 2026-09-05n hop 1 | `[]` | `eval_count=315`, empty `content`; thinking-channel ate the turn (2026-09-04r shape; agent already sends `think=false` on tool hops) |
| 2026-09-05n hop 2 | **`see_image`** | invented `language=python`; thinking treated README.md as an image |
| 2026-09-05at temp 0.0 / `think=false` / 67 schemas | **`see_image`** | CoT in `content`; invented `action=see_image` |
| same, `num_predict=128` | `[]` | truncated mid-reasoning toward `see_image` |
| same, **`read_file` schema only** | **`read_file`** `{path: local_agent/README.md}` | weights can emit the right call when the catalog is one tool |

So after a correct R1 tools template, the remaining failure is
**wrong-tool selection under the live ~67–68 tool GPU catalog** (catalog
drowning / R1 function-calling quality), not “Ollama never parsed the
call.” DeepSeek’s own guidance already calls R1 function calling
unstable.

## Why the Coder promoter cannot fix this

Coder (2026-09-05t): **correct tool, wrong wire format.**
`run_code` as standalone/fenced `{"name","arguments"}` in `content`;
Ollama wants `<tool_call>` XML; `parse_content_json_tool` lifts it when
native `tool_calls` is empty.

DeepSeek after retag: **correct-enough wire format, wrong tool.**
Hop 2 already populated native `tool_calls` (`see_image`). The promoter
is gated on empty native calls and a **whole-message** JSON object. Live
DeepSeek `content` is CoT prose or empty — never that JSON.

Offline re-run of `parse_content_json_tool` against the saved hops
(full GPU schemas): **all `None`**

- `2026-09-05_deepseek_one_more/probe.json` (full-schema CoT, truncated
  CoT, even the one-tool hop’s prose)
- `2026-09-05_template_retag/deepseek_native.json` (`content=""`,
  `fenced_json_in_content=false`, `has_tool_call_xml=false`)

Widening the promoter to harvest JSON out of CoT, or to override an
already-wrong native `see_image` call, would be a new unsafe parser —
not the Coder fix.

## Alternatives considered (none simple + low-risk)

| Idea | Why not |
|---|---|
| Point `DEEPSEEK_MODEL` at `:r1-tools` | Native calls fire, but they pick `see_image` on a markdown README. Untrustworthy; not a promotion. |
| Pull `MFDoom/deepseek-r1-tool-calling:14b` | 1y stale; own readme copies DeepSeek’s “unstable FC” notice; 9 GB non-abliterated. Already rejected in 2026-09-05at. |
| DeepSeek-only reduced schema | One-tool control works, but that is a DeepSeek crutch. Huihui-14B already picks `read_file` from the full catalog (2026-09-05b/bn). Would be a `router.py` / profile change. |
| `CODING_RULES` / `TOOL:` prompt | Explicitly ruled out since 2026-09-05g. |
| Move `CAP_LOGIC` to Huihui | Operator decision, not a template fix. Out of scope here; no routing edit. |

## Outcome

**Close as not viable.** Keep production DeepSeek on the Huihui tag as a
reasoning specialist (`CAP_LOGIC` unchanged). Do not retag, do not
extend the content-JSON promoter, do not pull another R1 tools image.
Tool-using logic hops remain a Huihui-14B choice, not another DeepSeek
experiment. The Coder parser path is unrelated and stays.

No GPU load this pass (template `show` + promoter replay on saved hops
only).
