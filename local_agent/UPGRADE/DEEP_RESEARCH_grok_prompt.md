# Grok agent prompt — add a `deep_research` tool with a pluggable search backend

Paste into Grok (or any coding agent). Work in the repo
`COMFYUI_STORY_HANDOFF_2026-08-09/`, in `local_agent/`. Read `local_agent/tools.py`
(especially `web_search`, `fetch_url`, the `_TOOLS` registry and `_SCHEMAS`),
`local_agent/agent.py`, `local_agent/router.py`, and `local_agent/README.md` before
writing anything. **Constraints:** Python stdlib only for the default path (no new
pip deps); the local HTTP server stays on `127.0.0.1`; `tools.py` stays a fixed
whitelist; never start a render or ComfyUI; never delete anything.

## Goal

Give the local agent a real **deep research** capability: from one question, it plans
sub-queries, gathers multiple web sources, and returns a synthesized, **cited** answer
— bounded so it can't run forever. And build it so the **search backend is swappable**:
DuckDuckGo (no API key) is the default now; a real search API (Brave / Serper /
Tavily / xAI) can be dropped in later by config, without touching the research logic.

## Part 1 — a pluggable search backend (the seam that makes the future API swap trivial)

Today `web_search` is hard-wired to scrape `lite.duckduckgo.com` and returns a blob of
text. Refactor the search behind a small interface:

- Define `SearchBackend` with `search(query: str, max_results: int) -> list[dict]`,
  each result `{"title": str, "url": str, "snippet": str}`. Returning **structured
  results with URLs** is the important change — `deep_research` needs URLs to fetch.
- `DuckDuckGoBackend` — refactor the current DDG logic to parse the lite results page
  into `{title,url,snippet}` items (keep the existing error handling: no-internet,
  rate-limited, zero-results, parse-failure — never silently empty). Stdlib only.
- Backend selection: `EQUAL_SHARES_SEARCH_BACKEND` env (default `"duckduckgo"`) chooses
  the class from a registry dict. Leave clearly-marked stubs for `brave` / `serper` /
  `tavily` that raise a helpful "set EQUAL_SHARES_SEARCH_API_KEY and enable this backend"
  message — **do not implement the keyed APIs now**; just make adding one a ~20-line
  class + a registry entry + an env var. Document this in a comment and the CHANGELOG so
  the later swap is a config change, not a rewrite.
- Keep `web_search` working: have it call the selected backend and format the results as
  text (so existing callers/tests still pass), but now backed by the interface.

## Part 2 — the `deep_research` tool

Add `deep_research` to `tools.py` (registry entry in `_TOOLS` + a JSON schema in
`_SCHEMAS`). Signature: `{"question": str, "max_rounds": int (default 2, cap 4),
"max_sources": int (default 6, cap 12)}`.

Algorithm (bounded, deterministic control flow — the agent's reasoning model does the
thinking, the tool does the orchestration):

1. **Plan** — call the local reasoning model (reuse the existing agent/model path via
   `router`/`ollama_client`; do NOT re-implement model calling) to turn the question
   into 3–5 focused sub-queries. If the model is unavailable, fall back to using the
   question itself as a single query (say so in the output).
2. **Gather** — for each sub-query, `backend.search(...)`, collect unique URLs up to
   `max_sources`. Skip binaries/duplicates. Respect the DDG rate-limit backoff already
   in the code.
3. **Read** — `fetch_url` each selected source (reuse the existing function; it already
   strips HTML, caps size, refuses binaries, and reports redirects). Keep per-source
   text short (e.g. 2–3k chars) so the synthesis prompt fits the context window.
4. **Synthesize** — one more model call: given the question + the collected
   `{url, title, extract}` set, produce a concise answer that **cites each claim with the
   source URL** and lists the sources at the end. Explicitly instruct the model to say
   what it could NOT verify and to not invent facts — matching this project's
   evidence-first rule.
5. **Return** JSON: `{"question", "answer", "sources": [{title,url}], "sub_queries",
   "rounds_used", "backend", "notes"}`. If `max_rounds > 1` and the answer flags gaps,
   run one more targeted round on the missing pieces, then stop at the cap.

Bounds & safety: hard-cap rounds, sources, and total fetches; a wall-clock/размер budget
so a run ends predictably. It only reads the web and calls the local model — it never
writes files, renders, or calls state-changing tools. Failures degrade gracefully
(no internet → return a clear message + whatever local `search_docs` found, if relevant).

## Part 3 — resource awareness

The synthesis/plan calls hit the local reasoning model, which is heaviest on the GPU
14B. `deep_research` must obey the same rules as normal chat: it routes through the
existing `router` (GPU when idle, CPU 8B when a render owns the card), and it must not
force the GPU while a render is running. Note in the tool description that a deep run is
token-heavy and best when the GPU is free.

## Verify (show commands + output)

- `python local_agent/test_native_tool_calling.py` — still green (the schema/enum count
  test must include the new tool; update the expected count).
- New stdlib test (mock the backend + `fetch_url` + the model call): `deep_research`
  returns structured `answer` + `sources`, respects `max_sources`/`max_rounds` caps, and
  cites the mocked URLs; a no-internet backend yields a clean message, not a crash.
- New test: `EQUAL_SHARES_SEARCH_BACKEND=duckduckgo` selects the DDG backend; an unknown
  backend name raises the helpful error; a stubbed keyed backend reports "needs API key".
- `web_search` still returns text results (back-compat) via the new interface.
- `validate_h3_prompt.py` still 124/124.

## Record it

Write `CHANGELOG/<today>_deep_research_tool.md` — what changed, why, the test output,
and what's unverified (a live multi-source run needs internet + the GPU model). Add the
tool + backend selection to `local_agent/README.md`, and note in
`local_agent/UPGRADE/BUILD_STATUS.md` that the pluggable backend is in and the
"switch the search backend API" item is now a config change (set
`EQUAL_SHARES_SEARCH_BACKEND` + an API key), not new plumbing.
