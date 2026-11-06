# 2026-08-30 — Independent verification of 2026-08-30f corrections

Senior software verification engineer pass over the `2026-08-30f_corrections.md`
change record, which claimed "41 tests, 0 failures."

No new code was written in this session. All actions were read-only checks and
the test runner.

---

## Verified claim: 41 tests, 0 failures

**CONFIRMED.**

### Exact test command

```
cd local_agent
python -m unittest test_powerinfer_openai_proxy test_powerinfer_chat_route test_powerinfer_pipeline
```

### Result

```
Ran 41 tests in 0.206s
OK
```

Counts:
- Collected: 41
- Passed: 41
- Skipped: 0
- Failed: 0
- Errors: 0

The single `skipTest` present in the source
(`test_encrypt_roundtrip_with_env_key`, guarded by `vault._CRYPTOGRAPHY_AVAILABLE`)
did NOT trigger — the `cryptography` package is installed. The test ran fully.
Zero tests were suppressed, xfailed, or conditionally skipped.

---

## Files changed — match confirmed

| File | Stated change | Verified |
|---|---|---|
| `tools/powerinfer/models.json` | `relu-llama-7b.chat_format`: `"llama2"` → `"raw"` | PASS |
| `tools/powerinfer/record_acceptance_gate.py` | `_render_prompt` `"raw"` branch added | PASS |
| `local_agent/powerinfer_openai_proxy.py` | default stop `["</s>","[INST]"]` injected | PASS |
| `local_agent/router.py` | PowerInfer picker `kind`: `"chat"` → `"base_completion"` | PASS |
| `local_agent/test_powerinfer_openai_proxy.py` | +2 tests for default/caller stop | PASS |
| `local_agent/test_powerinfer_chat_route.py` | +1 test for picker `kind` | PASS |
| `local_agent/test_powerinfer_pipeline.py` | +2 behavioral tests for raw format | PASS |
| `CHANGELOG/2026-08-30d_quality_review_responses_recorded.md` | `[CORRECTED 2026-08-30f]` annotation present | PASS |
| `CHANGELOG/2026-08-30f_corrections.md` | All required sections present | PASS |

---

## Behavioral verification (independent, not doc-consistency)

### 1. Base-completion classification
- `pipeline_lib.target_config("relu-llama-7b")["class"]` == `"base"` ✓
- `pipeline_lib.target_config("relu-llama-7b")["chat_format"]` == `"raw"` ✓

### 2. PowerInfer routing
- `router.chat_models()` entry for `powerinfer-local` has `kind: "base_completion"` ✓
- Heretic and other chat entries still have `kind: "chat"` (unchanged) ✓

### 3. Stop-sequence defaults (proxy)
- `completion_payload({messages: [...]})` → `payload["stop"] == ["</s>", "[INST]"]` ✓
- `completion_payload({..., "stop": ["DONE"]})` → `payload["stop"] == ["DONE"]` ✓
- Non-list `stop` still raises `ProxyError` ✓
- `max_tokens` clamping unchanged ✓
- `render_llama2_chat()` still applies `[INST]` for chat-class calls ✓

### 4. Acceptance gate prompt rendering
- `_render_prompt([], "hello", "raw")` → `"hello"`, no `[INST]` ✓
- `_render_prompt([], "hello", "llama2")` → `"<s>[INST] hello [/INST]"` (unchanged) ✓
- `_render_prompt([], "hello", "llama3")` → llama3 header format (unchanged) ✓

---

## Syntax and import checks

All 6 modified Python files passed `ast.parse()`. All 3 modules imported cleanly:

- `local_agent/powerinfer_openai_proxy.py` — import OK
- `local_agent/router.py` — import OK
- `tools/powerinfer/record_acceptance_gate.py` — import OK

---

## Protected files — not modified

| File | Status | Notes |
|---|---|---|
| `validation/quality_review_packet.json` | Intact, `status: "responses_recorded"` | Unmodified |
| `validation/acceptance_gate_20260830_175953.json` | Intact, `promoted_to_picker: false`, 9/9 checklist true | Unmodified |
| `PowerInferStaging/.../manifest.json` | Intact, `class: "base"` | Unmodified |

No GGUF, predictor, activation, or production registry was touched.

---

## Broader test suite (pre-existing state check)

These suites were run to confirm the `router.py` and proxy changes did not
break adjacent code:

| Suite | Command | Result |
|---|---|---|
| Router switching | `python -m unittest test_router_switching` | Ran 41 tests, OK |
| Native tool calling | `python -m unittest test_native_tool_calling` | Ran 28 tests, OK |
| LXMF bridge | `python -m unittest test_lxmf_bridge` | Ran 13 tests, OK |
| Media analysis | `python -m unittest test_media_analysis` | Ran 20 tests, **1 pre-existing failure** |

The `test_media_analysis` failure
(`test_existing_whisper_capability_routes_transcription_without_loading_a_model`)
passes in isolation but flakes under combined module load. This is a test-ordering
isolation issue that pre-dates these changes: `test_media_analysis.py` was last
modified `2026-08-30 02:25` while the submissions changes are all `2026-08-30 19:49+`.
None of the changed files are imported by `test_media_analysis.py`.

---

## Discrepancies found

None. All stated changes are present and correct. The test count of 41 is confirmed.

---

## Conclusion: repository is safe to continue from

The submitted change record is accurate. All behavioral corrections are
in place, all tests pass, no evidence or protected files were modified, and
the broader routing and tool-calling suites are unaffected.

**One outstanding pre-existing issue (not introduced by this submission):**
`test_media_analysis` has a flaky test when run alongside other test modules.
This is an existing isolation bug unrelated to the PowerInfer corrections.
