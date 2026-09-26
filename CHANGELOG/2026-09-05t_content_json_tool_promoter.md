# 2026-09-05t — Content-JSON tool promoter (Qwen2.5-Coder parser gap)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05t**. Follows
`CHANGELOG/2026-09-05n` (official Coder template still left
`message.tool_calls` empty). Parser addition only. No `CODING_RULES` /
prompt / `TOOL:`-fallback changes. `JOSIEFIED_CODER_MODEL` default
unchanged.

## What changed

When native `tool_calls` is empty, `agent.parse_content_json_tool` scans
the whole assistant message for a **standalone** JSON object
`{"name": <str>, "arguments"|"parameters": <obj>}` that matches an
**advertised** schema (name + required arg keys). Fenced ` ```json ` or
bare object. Rejects: prose wrapping, code blobs, malformed JSON, unknown
names, missing required keys, extra top-level keys, non-object arguments.

Wired in `agent.answer` after native calls and **before** the `TOOL:`
legacy parser. Note event:
`content JSON tool call promoted (Ollama did not emit native tool_calls)`.

ADR `docs/adr/0002-native-ollama-tool-calling.md` records the extra path.

## Tests

`test_native_tool_calling` + `test_capability_routing`: **108 OK**
(was 102; six new):

- fenced JSON promoted
- bare JSON promoted
- `parameters` alias promoted
- JSON-in-prose / fenced-plus-prose / Python-code blob rejected
- malformed / trailing junk / array / missing args / unknown name /
  missing required key ignored
- agent loop: fenced `run_code` JSON executes the tool, not the `TOOL:` path

## Live case 3 (`run_code` clamp)

GPU idle at start (64 MiB). Same clamp prompt as
`2026-09-05_task_completion`. Receipts:
`artifacts/benchmarks/2026-09-05_content_json_parser/`.

| Tag | elapsed | promoted | legacy | `run_code` executed |
|---|---|---|---|---|
| `josiefied-qwen2.5-coder-14b:official-tools` | 140.8 s | yes | no | **yes** (sandbox `AssertionError` on buggy `clamp(5,0,10)`) |
| stock `qwen2.5-coder:14b` | 178.9 s | yes | no | **yes** (same AssertionError) |

2026-09-05b/n had `run_code_count=0` because Ollama never lifted the JSON.
The promoter now runs that intended call. Later hops on both tags still
drifted into other standalone JSON (`capabilities`, `run_safe_check`) —
that is model tool-selection after the first result, not a parser miss.
The debug loop did not reach a passing clamp; the asked check was that
`run_code` **executes**.

GPU unloaded after (`keep_alive: 0`).
