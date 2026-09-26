# 2026-09-03u — CLAUDE.md session-handoff line + HANDOFF_STATUS caveats

## What changed

1. `CLAUDE.md` — after the Changelog filenames paragraph, added the session-start line pointing agents at `python scripts/write_handoff_status.py` / `HANDOFF_STATUS.md`. Points caveats at that file's header. Did **not** change any other CLAUDE.md content.

2. `scripts/write_handoff_status.py` — generated header now states the two caveats explicitly: open TODOs are checkbox first-lines only (wrapped continuations omitted); orphan/persistence sections are CHANGELOG/runbook-seeded, not live-probed. Section 2 intro repeats the first-line-only note.

3. Regenerated `HANDOFF_STATUS.md` via `python scripts/write_handoff_status.py` (2026-09-03 ~3:17 PM ET).

## Encoding / line endings

`CLAUDE.md` verified after edit: UTF-8 no BOM, CRLF-only (no LF-only lines), leading UTF-8 em dash (`E2 80 94`) intact, no `U+FFFD` replacement characters. Insert used byte-preserving write (`write_bytes` after `\r\n` rejoin), not a PowerShell string rewrite.

## Scope

No `outputs/equal_shares/` touch. No GROK_STATUS edit. No farm/GUI/GPU start. No live OS probe.
