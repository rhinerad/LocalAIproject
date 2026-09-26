# Claude Code prompt — retrieval over the whole doc tree (refreshed 2026-08-23)

Paste into your coding agent. Run from the repo root
(`COMFYUI_STORY_HANDOFF_2026-08-09/`). Read `local_agent/README.md`, `CLAUDE.md`,
`local_agent/agent.py`, and `local_agent/router.py` first.

## What this is (and what already changed since the original 02)

The original upgrade 2 had two halves. **Half one — raising `num_ctx` — is already
done** and must NOT be redone: the adaptive reasoning pair now sets context
per-model in `router.Decision.options()` (primary 14B → 20480, fallback 8B → 32768)
with predictive routing at ~16K tokens. **Do not blanket-edit `GPU_OPTIONS`
num_ctx** — that would fight the adaptive logic.

This prompt is the **half that was never built: retrieval.** Today the agent only
knows `knowledge/SYSTEM_PROMPT.md`, a compiled ~9.5 KB digest of a ~200 KB tree.
Ask about a specific CHANGELOG measurement or a paragraph of `H3_PROMPT_RULES.md`
and it either reads a whole file or guesses. Give it lexical search over the tree.

## Job 1 — a retrieval index, no model required

New file `local_agent/retrieval.py`. Index, chunked to ~800 tokens with ~100-token
overlap, chunk boundaries on headings where possible:

    docs/**/*.md      CLAUDE.md      README.md
    CHANGELOG/*.md    START_*.md     FINISH_LOCAL_AGENT.md
    local_agent/UPGRADE/*.md
    outputs/equal_shares/runtime/agent_questions.md

**Skip** `archive/`, `_QUARANTINE_*`, `*.BACKUP*`, and anything bannered SUPERSEDED
— those are deliberately not current and must never be retrieved as fact.

- **Scoring: BM25 in plain Python** (~40 lines). No `rank_bm25`, no `sklearn`,
  nothing to install — offline forever.
- Make the scorer swappable: `score(query, chunks)` behind a small interface with
  `LexicalScorer` as default, so upgrade 5's `EmbeddingScorer` drops in later
  without touching callers.
- Persist the index as JSON next to the code, keyed by each file's mtime + size;
  rebuild only changed files. Startup stays under a second.

## Job 2 — expose it as a tool

Add `search_docs` to `tools.py` (registry + schema), `{"query": "...",
"max_results": 5}`, returning the top chunks each with its **source file and
heading** so the agent can cite where a claim came from — a claim without a source
is not evidence in this project. It is a read-only tool; it never writes.

Update `CONVERSATION_RULES` in `agent.py`: for any question about a rule, a
decision, why something is the way it is, or project history — **search the docs
first**; `read_doc` stays for reading a whole named file.

## Job 3 — shrink the compiled brief

Now that retrieval exists, `build_knowledge_pack.py` should compile a **smaller**
brief: current state, the non-negotiable settings, the prompt schema, and the two
voice rules. Move the narrative out — retrieval fetches it on demand. Target
**under 6 KB**; report before/after. (This frees context budget under the adaptive
pair's window, which is the only interaction with the num_ctx work — do not change
the num_ctx values themselves.)

## Job 4 — a context-trim guard that respects the adaptive window

Add a guard: if a request's estimated tokens would exceed the **effective** window
for the chosen model (use `router.Decision.options()["num_ctx"]` /
`router.estimate_context_tokens`, which already exist), trim the **oldest**
conversation turns — never the system prompt, never the current turn — and emit a
`note` event when trimming happens. This complements the predictive 14B→8B switch;
it does not replace it.

## Verify (show commands + output; stdlib, mockable)

- Index builds over the real tree — report file count, chunk count, index size.
- Touching one file re-indexes only that file.
- `search_docs "why was the pace corrected to 2.5"` returns the 2026-08-17b
  CHANGELOG chunk in the top 3; `search_docs "duration ladder"` returns the right
  `H3_PROMPT_RULES` section.
- Archived / superseded docs never appear in results (add a test asserting this).
- `test_native_tool_calling.py` still green; `search_docs` schema registered.
- Brief is under 6 KB.
- `validate_h3_prompt.py` still **124/124**.

## Record it

Write `CHANGELOG/<today>_retrieval_over_tree.md` (what/why/evidence/verified/
unverified), add its row to `CHANGELOG/README.md`, mark UPGRADE 02 built in
`local_agent/UPGRADE/00_INDEX.md`, and add `retrieval.py` + `search_docs` to
`local_agent/README.md`. Note plainly that only the retrieval half of the original
02 was outstanding; the num_ctx half was already delivered by the adaptive pair.
