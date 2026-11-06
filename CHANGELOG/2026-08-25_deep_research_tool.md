# 2026-08-25 — pluggable search backend and deep_research tool

## What changed

- `local_agent/search_backend.py` introduces `SearchBackend.search(query, max_results) -> list[{title,url,snippet}]`.
  DuckDuckGo (stdlib scrape of lite.duckduckgo.com) is the default. Brave / Serper /
  Tavily / xAI are registered stubs that tell the operator to set
  `EQUAL_SHARES_SEARCH_API_KEY` and `EQUAL_SHARES_SEARCH_BACKEND`. Adding a keyed
  API later is a ~20-line class plus a registry entry — not a rewrite of research.
- `web_search` still returns a text blob for existing callers; it now formats
  structured backend results and keeps the same no-internet / rate-limit /
  zero-results / parse-failure messages.
- `deep_research` is a new whitelist tool: plan 3–5 sub-queries via
  `router.decide()` + `ollama_client.chat`, gather unique URLs up to
  `max_sources` (cap 12), `fetch_url` each (2.5k chars), synthesize a cited
  answer, optional second round on gaps, stop at `max_rounds` (cap 4) or 90s.
  Read-only. `keep_alive: 0` on internal model calls. Never forces GPU while a
  render owns the card.

## Why

Single-shot DuckDuckGo text was not enough for multi-source cited answers, and
hard-wiring DDG would have made a later Brave/Serper/Tavily/xAI swap a rewrite.

## Tests

```
python local_agent/test_native_tool_calling.py
python local_agent/test_search_backend.py
python local_agent/test_deep_research.py
python local_agent/validate_h3_prompt.py --dir outputs/equal_shares/prompts_native_r2v
```

- native tool calling: **19/19 passed** (schema set includes `deep_research`)
- search backend: **7/7 passed** (DDG parse, web_search text, env selection,
  unknown backend, keyed stub needs API key, zero-results, no-internet)
- deep_research: **5/5 passed** (cited mocked URLs, source/round caps,
  no-internet message, schema registration)
- H3 validator: **124/124 valid**

No render, no ComfyUI, no deletes, no new pip dependencies.

## Unverified

~~A live multi-source run needs internet plus the local reasoning model.~~

## Live verification (2026-08-25, GPU idle, ComfyUI down)

```
python -c "import tools; print(tools.deep_research({'question':'What is the official Python programming language website?','max_rounds':1,'max_sources':3}))"
```

- elapsed **58.5 s**
- backend **duckduckgo**
- routed **gpu/huihui_ai/qwen3-abliterated:14b**
- 5 sub-queries planned, 3 unique sources fetched (`python.org`, downloads, docs)
- answer: official site is https://www.python.org/
- Live `web_search` also parsed lite.duckduckgo.com into titled URLs.

This is one short factual question, not a quality claim for long adversarial research.
A keyed API backend (Brave/Serper/Tavily/xAI) is still a stub until an operator
sets `EQUAL_SHARES_SEARCH_API_KEY`.
