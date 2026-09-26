# 2026-09-03bf — Stop eval CPU Ollama :11435; Hybrid fail-closes again

Letter from `python scripts/next_changelog_id.py` immediately before write.

The 2026-09-03bb Stage 5 comparison started a CPU-only Ollama on
`127.0.0.1:11435` so Hybrid could run live-dense. That is a production
behavior change if left up: query embed succeeds, dense ranking turns
on. Stopped it. Dense-on remains its own deliberate decision.

Not because Hybrid is bad. Because an eval instance is not how you
enable it.

## Consumers checked before stop

Workstation `:11435` is **not** a farm-dashboard / `farm_status.json`
input. `dashboard/collect.py` and `farm_health.py` never mention 11435.
Mac `embed_chunks` uses the worker's own Ollama (`127.0.0.1:11434` on
the Mac), not this port. GUI `:8760` and dashboard `:8765` were not
listening. `farm_status.json` stayed `status=ok` / `workers_responding`
before and after. No established TCP clients on 11435; `/api/ps` on
11435 was `{"models":[]}`.

Other local consumers of `router.CPU_HOST` (compaction overflow
summarize, CPU chat fallback) would have used `:11435` if the agent GUI
were up. It was not. GPU Ollama `:11434` (pid 22632, parent `ollama
app.exe`) was left running.

## Stop

Killed the eval `ollama serve` started under
`OLLAMA_HOST=127.0.0.1:11435` / `OLLAMA_VULKAN=false` (pid 33892, parent
the 2026-09-03bb powershell). After stop: port **11435 closed**, port
**11434 still OPEN**, only the original GPU `ollama.exe serve` remains.

## Fail-closed confirmation

Live `HybridScorer` (no embed mock) vs `LexicalScorer` on three queries,
including the two regressions, then `tools.search_docs` itself:

- `cpu_11435_listening=False`
- `farm_reachable=True` `status=ok`
- Hybrid top-5 ids **matched** lexical on all three
- `_match_by` was `lexical` only (no `embedding` / `both`)
- `search_docs` returned 5 results each, no dense tags

Queries: changelog letter convention; stay on Ollama vs PowerInfer;
judge_transcript NotRegistered.

## The two regressions stay on the record

Do not average these into the 13/18 vs 12/18 net lift. They block
turning dense on for real:

1. **`phase1_stay_on_ollama`** — gold rank 1→9. Lexical #1 is the Phase 1
   close note (stay on Ollama). Hybrid's top-5 is older PowerInfer
   scaffold/pipeline/picker docs.
2. **`judge_not_registered`** — gold rank 2→12. Lexical #2 is the exact
   “Step 2 — root cause of NotRegistered” section. Hybrid keeps the file
   intro and drops that chunk.

Flagged on the embed path and in Known limitations of
`docs/ARCHITECTURE.md`, plus Stage 5 notes in `RAG_EVALUATION.md`,
`docs/hybrid_scorer_proposal.md`, and `TODO.md`.

No `APP_REVISION` bump. GUI not started. GPU not used.

## Files

- `docs/ARCHITECTURE.md` (embed path + known-limitations flag)
- `RAG_EVALUATION.md` Stage 5
- `docs/hybrid_scorer_proposal.md` 2026-09-03bb addendum
- `TODO.md` Phase 2 item 4 Stage 5 note
