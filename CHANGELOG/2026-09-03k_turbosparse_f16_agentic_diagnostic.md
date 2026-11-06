# 2026-09-03k - TurboSparse F16 agentic diagnostic; Q4 still FAIL; registry FAIL

Did not dump. Did not train predictors. Did not convert. Did not edit o_proj.
Did not write into the parked 20260830b tree. Did not mark accepted. Did not
write production_models.json. Canonical `validation\agentic_quality_gate.json`
left `failed_turn_1`. Kept original `validation\registry_attempt.2026-09-03.json`.

## Failure class

First invalid_json class: **e** (not JSON at all; garbled prose).

Runtime changes applied: grammar on Q4, ctx 2048, temp 0. Do not re-litigate Q4
unless hash changed; Q4 sha256 reconfirmed unchanged.

## Q4 - still FAIL after runtime fixes

- sha256 `59318ed894f16d791ee418cb1536ba9bab62a85986a6a7b112ce59b17436c98b` (reconfirmed)
- Canonical gate: turn1 FAIL / turn2 not run. `failed_turn_1` class e garbled prose.
- Grammar probe (empty-object GBNF): valid JSON `{  }` but empty object -> official check_exact FAIL `wrong_tool_call`.
- Nonempty grammar: still `invalid_json`.
- Gate PASS/FAIL: turn1 FAIL, turn2 n/a.

## F16 diagnostic

Bundle `A:\PowerInferModels\turbosparse-mistral-instruct\turbosparse-approved-20260902-182522`.
F16 `output\turbosparse-mistral-instruct.powerinfer.gguf` 14,787,775,552 bytes,
sha256 `14474bd8f1d76fa7246bca5b9b63312fd661807dbe56eda38223015f493678d2` (reconfirmed after leftover Get-FileHash PID 34764 stalled and was killed).

Stopped leftover server.exe first. nvidia-smi idle then start. Thermal `-gtt 82` not supported on this 5080 (warning). Started from `output` cwd:

`A:\PowerInferBuild\bin\server.exe -m <f16> -c 2048 --vram-budget 12 --host 127.0.0.1 --port 8080 -t 8`

No OOM. Loaded mostly-F16 7.39B, offloaded 6804 MiB FFN, reported VRAM 10392 MB. Listened 127.0.0.1:8080.

Official 2-turn capture (canonical packet, temp 0, same stops, NO salvage grammar):
`validation\agentic_quality_gate.f16_diagnostic.20260903.json`
- turn1 FAIL `invalid_json: Expecting value` class e
- turn2 n/a
- raw turn1 snippet: ` You are a local tool:` / repeated `You are a local tool.`

Second diagnostic, same generic JSON-object GBNF used on Q4 (not a forced expected tool_calls payload):
`validation\agentic_quality_gate.f16_diagnostic.grammar.20260903.json`
- turn1 FAIL `invalid_json: Expecting property name enclosed in double quotes` (opened `{` then newlines)
- turn2 n/a

Stopped server. Final nvidia-smi: 30 C / 57 MiB / util 0% (2026-09-03 03:45:45 ET).

## Registry FAIL

Refused register; manifest still `candidate`. Wrote
`validation\registry_attempt.2026-09-03b.json`. Provenance dump_samples=25000,
parked_ref=20260830b-untouched. Hashes reconfirmed.

## Parked

20260830b parked: untouched
Spot-check mtimes still 2026-08-30 (config.json 18:35:46 ET; newest abliteration_manifest.json 20:24:02 ET). No writes into that tree.
