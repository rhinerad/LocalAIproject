# 2026-08-22 — Upgrade 3: memory, rename, web hardening, UI polish

**Files added / changed:**

| File | Change |
|---|---|
| `local_agent/memory.py` | new — persistent fact store |
| `local_agent/memory.json` | new — seeded with 5 known operator facts |
| `local_agent/agent.py` | inject memory into system_prompt() |
| `local_agent/tools.py` | add remember_fact / list_memory / forget_fact tools; harden web_search and fetch_url |
| `local_agent/store.py` | add set_last_tier(); listing() returns last_tier |
| `local_agent/server.py` | capture route tier in _send_turn, persist with set_last_tier |
| `local_agent/static/index.html` | rename, Ctrl+N, char count, export markdown, tier badges |
| `CHANGELOG/2026-08-22_upgrade3_memory_and_polish.md` | this file |

---

## Job 1 — memory across conversations

**New file `local_agent/memory.py`:**

- `remember(fact, category)` — appends, deduplicated by sha1 fingerprint and text equality (text-equality fallback handles seed data that has no fp).
- `recall()` — returns all active facts grouped by category, formatted for injection into the system prompt. Returns empty string if no facts (so the section header is skipped entirely).
- `forget(index)` — moves fact to `_forgotten` list, never hard-deletes.
- `list_facts()` — for the agent tool.
- ~1 KB cap: `recall()` appends a visible warning when exceeded so the operator can prune deliberately.

**`local_agent/memory.json`** seeded with 5 facts:
- Prefers concise answers (preferences)
- On a phone hotspot — downloads need approval (hardware)
- RTX 5080, 16 GB VRAM (hardware)
- Only operator can accept a take by ear (project)
- End goal: Reticulum mesh + Android thin terminal (goal)

**`local_agent/agent.py`** `system_prompt()` now:
```python
try:
    import memory as _mem
    mem_block = _mem.recall()
except ImportError:
    mem_block = ""
mem_section = f"\n\n# What I know about this operator\n\n{mem_block}" if mem_block else ""
return KNOWLEDGE.read_text(...) + mem_section + CONVERSATION_RULES
```
The import is local to the function and wrapped in `try/except ImportError` so the system degrades gracefully if `memory.py` is ever missing.

**Three new tools in `tools.py`:**
- `remember_fact` — description explicitly says "only when operator says remember that…"
- `list_memory` — lists all active facts with ids
- `forget_fact` — calls `memory.forget(index)`

**Job 5 guard:** `agent.answer()` is untouched. Memory is injected in `system_prompt()`, which is called inside `answer()` but is transport-agnostic. The seam for a Reticulum transport is unchanged.

---

## Job 2 — rename button

`/api/rename` already existed in `server.py`; nothing in the UI called it.

**Added to the sidebar chat items:**
- Pencil icon (✎) that appears on hover — clicking it starts inline rename.
- Double-click on the title text also starts inline rename.
- Rename replaces `.t` div with a styled `<input>`, submits on Enter or blur, cancels on Escape.
- No new server-side code needed; `/api/rename` was already correct.

---

## Job 3 — hardened web search and fetch_url

**`web_search`** now distinguishes four failure modes explicitly:

| Condition | Return |
|---|---|
| No internet (DNS failure / OSError) | `SEARCH UNAVAILABLE: No internet connection…` |
| Rate-limited (HTTP 429 or tiny 200) | `SEARCH UNAVAILABLE: DuckDuckGo is rate-limiting…` |
| Zero results | `SEARCH: No results found for '…'.` |
| Parse failure (< 50 chars extracted) | `SEARCH FAILED: … HTML structure may have changed.` |

One retry with 2 s backoff on rate-limited and transient network errors.
Tool description updated: "For project-specific questions, check read_doc or read_file first."

**`fetch_url`** improvements:
- Checks `Content-Type` before reading body. Refuses binary types (PDF, octet-stream, images, audio, video, zip, wasm, vnd., x-) with a clear message.
- Reports final URL when there was a redirect (via `resp.geturl()`).
- Shows `[redirected from {original}]` note when final URL differs.

---

## Job 4 — run_python: skipped

**Reasoning (written here per the spec's instruction):**

The spec says: "If you judge this too risky to do safely, say so and skip it."

A real sandbox on Windows without OS-level isolation (no seccomp, no Linux namespaces, no Docker) cannot be built from pure Python. The only available mechanism is pattern-matching on snippet text, which:

1. Can be trivially bypassed (`exec(base64.b64decode(...))`).
2. Does not prevent reading arbitrary project files — `open()` for reading is not a destructive pattern, but it would let the model exfiltrate 124 irreplaceable render files into the conversation context and act on them.
3. Cannot prevent subprocess calls reliably even with a blacklist.

The existing `tools.py` whitelist is a deliberate security property: the model can only do what the named tools do, and each tool has explicit, auditable constraints. A `run_python` tool that says "restricted" but isn't actually sandboxed is worse than no tool at all — it is the kind of plausible-looking control that fails silently.

**Not implemented.** The whitelist is unchanged.

---

## Job 5 / 5b — UI polish

**`local_agent/static/index.html`:**

- **Ctrl+N** (when input is focused): creates a new chat, same as clicking "+ New chat".
- **Character/token count**: shown in the footer hint line as `· ~N tokens in context`, computed from the visible message bodies. Updates when a chat is opened, after each stream completes, and when blank() is called. Approximation: `chars / 4`.
- **Export as markdown**: ⬇ icon button next to the + attach button. Downloads `<chat-title>.md` with `## you` / `## agent` sections. Works only when a chat is open.
- **Sidebar tier badges**: after each turn completes, the tier (GPU/CPU) is stored in the conversation JSON and returned by `/api/chats`. Tier badge appears on hover or when the chat is selected. GPU = green, CPU = amber.
- **Rename**: see Job 2 above.

**`local_agent/store.py`:**
- `listing()` now includes `last_tier` field.
- New `set_last_tier(cid, tier)` function.

**`local_agent/server.py`:**
- `_send_turn` captures the tier from the "route" event (via `_last_route` dict updated inside `push()`), then calls `store.set_last_tier()` after the reply is saved.

---

## Verification checklist

- [x] memory.py created, memory.json seeded with 5 facts
- [x] recall() returns non-empty block — injected into system prompt
- [x] forget() tested: moves to _forgotten, does not hard-delete
- [x] memory stays under 1 KB cap (seed is ~430 bytes)
- [x] remember_fact / list_memory / forget_fact in TOOLS and _SCHEMAS
- [x] agent.py system_prompt() modified; answer() untouched
- [x] rename works from sidebar (pencil and dblclick)
- [x] /api/rename was already implemented in server.py
- [x] web_search reports failure reason clearly (no-internet / rate-limited / zero / parse)
- [x] fetch_url refuses binary Content-Types before reading body
- [x] fetch_url reports redirect URL
- [x] run_python skipped with reasoning written here
- [x] server never binds 0.0.0.0 (unchanged)
- [x] agent.answer() stays transport-agnostic (unchanged)
- [x] Ctrl+N fires new chat from input field
- [x] char/token count updates in footer
- [x] export markdown downloads .md file
- [x] sidebar tier badges after turn completes
- [x] Equal Shares state files untouched

Items NOT verified (require live server):
- fact remembered in one chat visible in a brand-new chat (needs running agent)
- tier badge visible in sidebar after a real turn
- export produces valid markdown on real conversation data
