# 2026-08-30 — README documents the PowerInfer picker contract

## What changed

`CHANGELOG/2026-08-30b_scope_reprioritization_doc_pass.md` left this open:

> `local_agent/README.md` does not yet mention the PowerInfer chat-picker
> integration … a real documentation gap

Closed that gap. Documentation only. Did not touch `router.py`,
`tools/powerinfer/`, or `work/`.

| File | Change |
|---|---|
| `local_agent/README.md` | New **Optional PowerInfer chat (`powerinfer-local`)** section next to Heretic: GPU-only, never a silent CPU substitute, router detects `127.0.0.1:8091` and `127.0.0.1:8080` and does not start them, where to look if the row is disabled. Files table: `powerinfer_client.py`, `powerinfer_openai_proxy.py`. Model-policy / "nothing to install" lines now name both opt-in picker rows. Symptom table row for a disabled PowerInfer entry. |
| this entry | records that the 2026-08-30b follow-up is done |

The section states what is **built** (picker contract, verified 2026-08-29/30)
versus what is **pending** (predictor calibration, no accepted production-
registry model, do not pin live). It does not call PowerInfer
production-ready.

## Why

Routing is a general-agent feature. The README already described Huihui 14B/8B
and Heretic in detail; PowerInfer is the same picker with a different
contract and was missing. After the 2026-08-30 scope reprioritization, that
omission mattered more, not less.

## The evidence

README now contains the picker label, ports, "does not start or stop them",
GPU-only / no Huihui substitute, and the pending-registry caveat. Files table
rows sit next to `ollama_client.py`. No code path changed.

## What was verified after

Read the new section, Files table, model-policy paragraph, and symptom row
back against `CHANGELOG/2026-08-29k_powerinfer_chat_picker.md` (ports, no
autostart, GPU-only) and `TODO.md` (calibration in progress, no accepted
registry model).

## What is still unverified

Live GUI pin against a real `server.exe` + proxy pair. Unchanged: no
accepted sparse bundle.
