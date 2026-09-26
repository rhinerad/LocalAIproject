# 2026-08-22 — Complete and live-verify native Ollama function calling

## Why this entry exists

`2026-08-19_native_function_calling.md` recorded an initial implementation but
explicitly left the live Ollama, two-call GUI, and desktop-regression checks
unfinished. This session completed those checks and fixed defects found while
auditing the implementation.

## Changes

- `local_agent/agent.py`
  - Native tool-result messages now include the required function `name`, so
    several results from one assistant turn are unambiguous.
  - Malformed legacy JSON is no longer silently converted to `{}` and executed.
    It becomes an error result and the tool is not run.
- `local_agent/ollama_client.py`
  - Malformed or non-object native arguments are marked invalid instead of
    silently becoming `{}`.
- `local_agent/router.py`
  - CPU preference now selects installed `qwen3:8b` before `dolphin3:latest`.
    `qwen3:8b` advertises Ollama's native `tools` capability; Dolphin3 does not
    and remains the legacy compatibility fallback.
- `local_agent/build_knowledge_pack.py`
  - Removed the last generated `TOOL: <name> <json-arguments>` protocol block.
    The compact replacement says only to prefer tools for current state,
    counts, clips, and files.
- `local_agent/README.md`
  - Updated model guidance for the native-calling path.
- `local_agent/test_native_tool_calling.py`
  - Added eight stdlib regressions covering schemas/enums, request transport,
    multiple calls in one hop, named results, legacy fallback, malformed JSON,
    all required guards, Stop, attachments, persistence, and regeneration.

No tool implementation or validation guard was relaxed. No model was downloaded.

## Live evidence

The GUI server ran at `127.0.0.1:8760`, routed to the CPU-only Ollama server at
`127.0.0.1:11435`, and selected installed `qwen3:8b`. Ollama `/api/ps` reported
`size_vram: 0` and `context_length: 8192`.

Question: `Compare the duration ladders for 00B and 00A. Use the current project data.`

- conversation id: `753ecd5835a44286`
- one native assistant turn emitted two calls:
  1. `duration_ladder {"clip":"00B"}`
  2. `duration_ladder {"clip":"00A"}`
- the SSE stream contained two `tool` events and two matching `tool_result`
  events before the prose answer, so the GUI rendered one action card per call.
- this is the previously observed failure case: `qwen3:8b` used to answer from
  memory when asked to emit a TOOL line. With native schemas it made both calls.

Desktop regression evidence:

- attachment/persistence conversation `384f60adacbc4155` stored the inlined
  `code.txt` content and answered `PERSIMMON`.
- Regenerate truncated and regenerated that conversation; it remained two
  messages and again answered `PERSIMMON`.
- Stop conversation `e77a0db328fb4f3a` returned `_[stopped]_` after the live
  `/api/stop` request.

## Verification

```text
python local_agent\tools.py                                      PASS (14)
tools.schemas() JSON/schema and exact enum assertions            PASS
python -m unittest -v local_agent.test_native_tool_calling       PASS (8/8)
unknown tool                                                    REFUSED
clip ../etc                                                     REFUSED
doc /etc/passwd                                                 REFUSED
build action rm -rf /                                           REFUSED
write_file outputs/equal_shares/manifest.json                    REFUSED
legacy TOOL fallback stub                                       PASS
malformed legacy JSON stub                                      REFUSED, tool not run
live native two-call GUI turn                                   PASS
live Stop / Regenerate / attachment / persistence               PASS
python local_agent\validate_h3_prompt.py --dir ...              124/124 valid
```

## Prompt-size measurement

- documented pre-native system-prompt baseline: approximately **13,000 chars**
- current exact `agent.system_prompt()`: **10,808 chars**, **1,731 words**
- reduction: approximately **2,192 chars**, or **548 tokens** using the project's
  stated four-characters-per-token estimate
- the final generated TOOL protocol removal accounted for **153** of those chars
- compact serialized native schemas: **4,984 chars** per request

The system prompt therefore reclaimed about 548 tokens, while the schema array
adds structured request tokens separately. Reliability improved despite the net
request-size increase: the live model made two structured calls where it had
previously answered from memory.

## Remaining scope

No Equal Shares render was started and no render evidence was modified. GPU-tier
native calling was not needed for this CPU-only verification; the live required
GUI path and the installed model that previously failed are both verified.
