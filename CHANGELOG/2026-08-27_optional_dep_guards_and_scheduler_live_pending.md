# 2026-08-27 — optional-dependency guards; scheduler live test pending

## What changed

### Job 2 — optional package import guards (complete)

Four files modified, one new test file created.

#### `local_agent/exemplar_embeddings.py`

The two chromadb imports (`import chromadb` and `from chromadb.config import
Settings`) were bare top-level statements. Any missing or broken chromadb
installation raised `ImportError` at import time, preventing `agent.py` and
`server.py` from loading at all.

**Change:** wrapped in try/except ImportError. On failure: `_CHROMADB_AVAILABLE
= False`, `_CHROMADB_REASON` carries the package name and install command.

Five public functions guarded:

| function | behaviour when chromadb absent |
|---|---|
| `retrieve()` | raises `RuntimeError(_CHROMADB_REASON)` — not silently empty |
| `semantic_duplicate()` | returns `{"available": False, "reason": ..., "install": ...}` |
| `embed_record()` | returns `{"status": "unavailable", "reason": ..., "install": ...}` |
| `sync_approved()` | returns `{"embedded": 0, "unavailable": True, "reason": ...}` |
| `start_worker()` | returns immediately; no background thread starts |
| `_client()` | raises `RuntimeError(_CHROMADB_REASON)` (private guard for any missed path) |

`retrieve()` raises rather than returning `[]` because the existing caller in
`agent.py` already has `except Exception` around it and emits a named note.
Returning `[]` would be silent; raising is not.

#### `local_agent/feedback_manager.py`

`from cryptography.hazmat.primitives.ciphers.aead import AESGCM` was a bare
top-level import. Missing cryptography prevented `server.py` from loading.

**Change:** wrapped in try/except ImportError. On failure: `_CRYPTOGRAPHY_AVAILABLE
= False`, `_CRYPTOGRAPHY_REASON` carries the package name and install command.

Four public functions guarded:

| function | behaviour when cryptography absent |
|---|---|
| `decrypt_envelope()` | returns `{"available": False, "reason": ..., "install": ...}` |
| `flush_pending()` | `_encrypt()` raises `RuntimeError`; flush re-raises it; no unencrypted file is written |
| `start_idle_worker()` | returns immediately; no background thread starts |
| `status()` | returns `{"available": False, "last_error": _CRYPTOGRAPHY_REASON, ...}` |

`enqueue()` is unchanged: it puts a record on `_PENDING`. If `flush_pending`
cannot encrypt, it leaves the record in the queue and re-raises — the record
stays in RAM and is never silently dropped or written in plaintext.

#### `local_agent/capabilities.py`

Two new capability entries added to `capability()` and `all_capabilities()`:

- `"exemplar_retrieval"` — `importlib.util.find_spec("chromadb") is not None`;
  reports install command when absent.
- `"feedback_encryption"` — `importlib.util.find_spec("cryptography") is not
  None`; reports install command when absent.

`all_capabilities()` now covers 8 names: vision, video_frames, audio_measure,
transcription, voice_compare, qwen_image_diffusion, exemplar_retrieval,
feedback_encryption.

#### `local_agent/test_optional_deps.py` (new)

22 tests in 4 classes:

- `TestChromadbGuard` (7) — reloads `exemplar_embeddings` with `sys.modules["chromadb"] = None`; checks flag, reason, and each public function's degraded response.
- `TestCryptographyGuard` (6) — reloads `feedback_manager` with `sys.modules["cryptography"] = None`; checks flag, reason, `status()`, `decrypt_envelope()`, `flush_pending()` re-raise path, and `start_idle_worker()`.
- `TestCapabilitiesReporting` (6) — checks `all_capabilities()` contains both new keys; skip-guards for installed/absent paths.
- `TestAgentImportsSurvive` (3) — subprocess imports of `agent` and `server` with top-level packages blocked via `sys.modules` stubs; confirms `ok` on stdout.

## Verified after

```
python -m unittest test_optional_deps -v
```
```
Ran 22 tests in 6.695s
OK (skipped=2)
```

The 2 skips are the "absent path" capability tests for chromadb and cryptography,
which only fire when the packages are actually missing. They are correct skips on
this machine.

```
python -m unittest test_phone_scheduler -v
```
```
Ran 10 tests in 0.635s
OK
```

```
python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v
```
```
124/124 valid
```

```python
import tools; schemas = tools.schemas(); print(len(schemas))
```
```
48
```

All four regressions clean.

## Still unverified

### Job 1 — live scheduler delivery to the real phone

The phone was not available for a live test in this session. What remains:

1. Start the Sideband bridge and confirm the paired phone is active.
2. Ask in plain language: "message me every 15 seconds five times, counting up
   from 0."
3. Observe whether the model calls `schedule_phone_messages` unprompted.
4. Confirm five messages arrive on the phone at roughly 15-second spacing,
   counters 0–4, with no sixth message.
5. Test cancel: call `list_phone_schedules` from the phone, then
   `cancel_phone_schedule`; confirm delivery stops.
6. Test restart: start an active schedule, stop and restart the bridge, confirm
   it resumes without double-sending missed intervals.

If the model narrates instead of calling the tool, the fix is in the tool
description in `tools.py` and the `CONVERSATION_RULES` in the system prompt —
not in the wiring, which is confirmed working by `test_phone_scheduler`.

**No live measurement was recorded for Job 1.** This entry does not claim the
phone received any message.

---

# 2026-08-27 — tool description collision fix

## What changed

**`local_agent/tools.py`** — two tool description strings modified.

### The observed problem

A 26-message phone conversation (`chats/87017e91b2ab4fac.json`, model
`huihui_ai/qwen3-abliterated:14b`) showed the model systematically choosing
`start_current_chat_render` over `schedule_phone_messages` when the user asked
to "send me a message every 10 seconds for 20 minutes, counting from 0".

The model responded with text descriptions of `start_current_chat_render
--duration 1200 --interval 10 --start 0` starting at message 5 and never
deviated. The user echoed the model's own output back three times. When the user
said "yes" at message 24, the model actually called `start_current_chat_render`
and received an H3 prompt-set error.

The model never called `schedule_phone_messages` once. The wiring is confirmed
working by `test_phone_scheduler` (10/10 green) and by `phone_schedule_audit.jsonl`
which shows earlier sessions successfully queuing messages to LXMF.

### Root cause

The `schedule_phone_messages` description ended with a single low-signal hint:
`Use for "message me every N seconds/minutes".` That hint appeared at the end
after the JSON schema and interval constraints, where it competed with the
H3-render context that saturated the system prompt from CLAUDE.md.
`start_current_chat_render` contained no explicit exclusion for messaging tasks,
so the model picked the more structurally prominent render tool and reinterpreted
`interval 10`, `duration 1200`, and `start 0` as render parameters.

### Change — `schedule_phone_messages`

Old (end of string):
```
interval 10-3600s, count 1-120, within 24h. Use for "message me every N seconds/minutes".
```

New (full replacement):
```
PERIODIC TEXT MESSAGES TO THIS PHONE — call this tool whenever the caller asks
to "send me a message every N seconds/minutes", "message me every", "text me
every", "keep messaging me", or "count up to me". This is NOT video rendering;
it sends repeating text messages back to the caller's phone only — the recipient
is always the caller and cannot be changed. {...schema...} interval 10-3600s,
count 1-120, within 24h.
```

All triggering phrases from the failure conversation are now named explicitly at
the front of the description. The anti-collision note `NOT video rendering`
appears in the body.

### Change — `start_current_chat_render`

Old (beginning):
```
Prepare and start the current chat's latest complete H3 prompt set...
```

New (beginning):
```
GPU VIDEO RENDERING ONLY — use this tool ONLY when the operator explicitly says
'render it' or 'start render' for H3 video generation. Never use this tool to
send periodic text messages or any other messaging task. Prepare and start...
```

The explicit exclusion eliminates the residual ambiguity that let the model
reinterpret a scheduling request as a render command.

## Verified after

Read-back of lines 1270 and 1280 confirmed the strings are in place. No
functional code was changed; the tool implementations are unchanged. Schema
count unchanged at 48.

## Still unverified

Whether the description change alone is sufficient to overcome `huihui_ai/
qwen3-abliterated:14b`'s tendency to latch onto the render tool when the system
prompt is heavy with CLAUDE.md render rules. This requires a live test: start a
fresh phone conversation with no prior render context, ask "send me a message
every 15 seconds five times counting from 0", and confirm the model calls
`schedule_phone_messages` without narrating.
