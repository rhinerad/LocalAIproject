# Docs-only: FlashRank catalog names, Swarm checkbox rollup, ARCHITECTURE re-read

Date: 2026-09-03. Docs only; no code changed.

## What changed

- `TODO.md` Phase 2 item 4 Stage 3 and `RAG_EVALUATION.md` open question 1 no longer name `ms-marco-MiniLM-L-6-v2` as a FlashRank model. Catalog-correct options are `ms-marco-TinyBERT-L-2-v2` (default) and `ms-marco-MiniLM-L-12-v2` (larger). See `docs/hybrid_scorer_proposal.md`.
- `TODO.md` Phase 2 item 5 (Swarm offload) parent checkbox rolled up `[~]` → `[x]` because every child item was already `[x]`. Body text otherwise untouched.
- `docs/ARCHITECTURE.md` re-read against current `retrieval.py` (HybridScorer is `_DEFAULT_SCORER`; embed farm path unchanged), `agent.py` (2026-09-03a main-thread tool-exception handling), and `farm_offload.py` (still no `farm_health` pre-flight).

## CLAUDE.md audit (no edit)

- `SCOPE NOTICE` appears once as the actual notice (top of file). Later "Superseded 2026-08-30 — see the SCOPE NOTICE" banners on Current job / Do not interrupt / Persistence are pointers, not a second notice.
- Changelog filename convention (`YYYY-MM-DDx_`, `scripts/next_changelog_id.py`) appears once under `CHANGELOG/`.
- No unambiguous duplicate and no contradiction found; file left unchanged.

## Verification

Mechanical string replacements with occurrence-count checks (exactly one match each). No tests, no code.
