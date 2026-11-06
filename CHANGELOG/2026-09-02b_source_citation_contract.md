# 2026-09-02b — Source citation contract for factual claims

## What changed

The local agent now requires source-backed factual claims and preserves
provenance through context pruning.

## Files modified

### `local_agent/agent.py`

- Added `# Source citation` section to `CONVERSATION_RULES` (between the
  tool-mechanics silence rule and the scoped-project-docs rule). Contract:
  - **Web / internet** claims must include the URL or page title.
  - **Project documents** claims must cite file path and section heading.
  - **Files and system state** must name the file path or directory.
  - **Memory and prior chats** must note that provenance.
  - **Unsupported pre-training knowledge** must be labelled "from model
    knowledge" or "unverified".
  - Exception: casual chat, creative writing, brainstorming, and code
    generation do not require source labels unless a specific factual claim
    is being made within them.

- Added `_tool_source_label(name, result) -> str | None` — extracts
  provenance from the raw tool result string for the six tracked tool types:
  - `fetch_url` → final URL from leading `[url]` bracket
  - `web_search` → backend + query from leading `[backend: query]` bracket
  - `search_docs` → `"docs: path1, path2, path3"` from JSON `source` fields
  - `read_file` → file path from leading `[File: path]` header
  - `list_dir` → directory path from first line of result
  - `list_memory` / `remember_fact` → `"persistent memory"`
  - All other tools → `None` (no label, no format change)

- Updated the post-tool follow-up user message: now instructs the model to
  "cite the source (URL, file path, or tool name) visible in the tool
  results above; label unsupported conclusions 'unverified' or 'from model
  knowledge'."

- Updated both `prune_large_text` call sites (main tool loop and specialist
  retry path) to pass `source_label=_tool_source_label(name, result)`.

### `local_agent/artifacts.py`

- `prune_large_text(kind, text, limit=2400, source_label=None)` — added
  optional `source_label` keyword argument (backward compatible; default
  `None` preserves the existing pointer format for all callers that don't
  pass it).
- Pruned pointer now embeds `source=<label>` when a label is supplied:
  `[{kind} output pruned; source={label}; artifact_id={id}; stored locally; original_chars={n}; sha1={sha}]`
- When `source_label` is `None` the pointer format is unchanged; existing
  tests and callers are unaffected.

### `local_agent/tools.py`

- `read_file()` — prepends `[File: {resolved_path}]\n\n` before content so
  `_tool_source_label` can extract the path from the tool result string.
- `list_memory()` — prepends `[Source: persistent memory]\n` to both return
  paths (empty and populated) so provenance is present in the model context.

### `local_agent/test_source_citation.py` (new — 24 tests)

| Class | Tests |
|---|---|
| `SourceLabelExtractionTests` | 11 — extraction from fetch_url (plain and redirect), web_search, search_docs (with and without results), read_file, list_dir, list_memory, remember_fact, untracked tool, GPU tool |
| `ArtifactSourceLabelTests` | 4 — source label in pruned pointer, no label leaves format unchanged, small result returned as-is, label survives a real fetch-sized result |
| `ToolResultSourceHeaderTests` | 3 — read_file has `[File: …]` header, header is label-extractable, list_memory has `[Source: persistent memory]` header |
| `AgentCitationContractTests` | 5 — CONVERSATION_RULES contains `# Source citation`, covers web/internet, project docs, memory, creative exception |
| `NoStaleSpecialistSourceTests` | 1 — specialist scope guard discards stale H3/ComfyUI reply; final answer contains neither "Equal Shares" nor "batch_render" |

## Test results

```
python -m py_compile local_agent/agent.py local_agent/tools.py local_agent/artifacts.py
# exit 0 — no syntax errors

python local_agent/test_native_tool_calling.py
# Ran 57 tests in ...s — OK (0 failures, 0 errors)

python local_agent/test_source_citation.py
# Ran 24 tests in ...s — OK (0 failures, 0 errors)
```

## Remaining gaps

- The browser GUI does not yet render source metadata as distinct visual
  cards. The provenance label is present in the model reply text but has no
  dedicated UI treatment.
- `list_dir` provenance relies on the first line of the result being the
  directory path. If that format changes, the label extraction breaks silently.

## What was not started

No GPU workload, ComfyUI instance, render, model load, Ollama inference,
PowerInfer process, or download was initiated.
