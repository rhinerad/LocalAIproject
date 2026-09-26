# 2026-09-05be — Status sync: catalog-drowning fix proposed, flag button live, Android companion scoped

## Scope

Operator-facing tracking entry for three reports
(`2026-09-05bc`/`bd`/`bb`). No new production work from this entry.

## 2026-09-05bc — Catalog drowning confirmed cross-model, real fix proposed

Real, important finding, not built yet. Catalog drowning is not
DeepSeek-specific: Huihui-14B itself picks the wrong tool
(`fetch_url` on a local markdown file) once the full 68-tool project
schema is loaded, despite picking correctly on a smaller 54-tool
general schema in the original 2026-09-05b test. Only `gpt-oss-20b-heretic`
resisted drowning in this probe, and it separately needs >=8k context
just to hold the catalog.

The 14B->8B demotion is confirmed real, not a farm-outage artifact: the
router's token estimator (`len(json)/3.4`) overestimates Qwen's actual
schema cost by roughly 2-3x, which can falsely demote a 14B model that
would have actually fit within context. Two independent proposed fixes,
neither a DeepSeek-only crutch: (1) a curated core-tool subset for
tool-classified local-GPU-fallback hops specifically (not shrinking
every Huihui conversation), and (2) replacing the token estimator with a
measured per-schema constant instead of the current length heuristic.
Recommendation is to do both, with the curated-subset change scoped to
fallback hops only until measured safe more broadly.

## 2026-09-05bd — Intent-mismatch flag button shipped

Real and ready to use now: a "this wasn't what I meant" button on
assistant messages in the desktop GUI, appending one JSONL record
(`local_agent/runtime/intent_mismatch.jsonl`) with the triggering
message, full reply, tool calls, and routing decision — no model re-run,
no routing/prompt change, no memory write. 17/17 tests pass. Needs one
desktop-agent restart to pick up the new endpoint. This directly answers
the operator's "start gathering data" request from earlier today — using
it during normal usage is what builds the real before/after dataset the
original TODO item needs.

## 2026-09-05bb — Android companion scoped, real security-first design

Passed 2 review rounds (15 issues addressed), 0 open. Correctly refuses
several tempting shortcuts: no `MANAGE_EXTERNAL_STORAGE`, no APK
installation over LXMF/Wi-Fi/LoRa (specified as APIs that must not
exist, not just policy), a lost-phone honesty note (a still-paired phone
is a live client with ungated reads until revoke — same residual-risk
class as the edge-gateway's "queued prompt is readable" note). 14-item
sign-off list (A1-A14) required before any Android compile, ADB install,
or production-agent edit.

## Status

Task #53 (Android companion scope) closed. Task #55 (catalog drowning
audit) closed with a real, unbuilt fix proposal awaiting authorization.
Task #56 (flagging mechanism) closed and shipped.
