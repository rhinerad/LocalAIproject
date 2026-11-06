# 2026-09-03j — handoff-status generator

Date: 2026-09-03. New stdlib script only. `CLAUDE.md` was **not** edited. `GROK_STATUS.md` was **not** updated. No `outputs/equal_shares/` touch. Did not start the GUI, GPU jobs, or farm processes. Did not live-probe OS processes for the orphan/persistence lists.

## What changed

New `scripts/write_handoff_status.py`. From the repository root:

```
python scripts/write_handoff_status.py
```

overwrites `HANDOFF_STATUS.md` at the repo root (never appends). Optional `--output` for tests/debug. Re-run is idempotent: a fresh file from current sources, no duplicate sections.

Generated file sections: recent lettered CHANGELOG (last ~15, newest first), open `TODO.md` checkboxes (`[ ]` / `[~]` verbatim), seeded orphaned leftover infrastructure, and documented persistence for WireGuard / Celery / tunnel_relay / Redis-Docker. Farm *procedures* are pointed at `docs/FARM_HEALTH_RUNBOOK.md` and `docs/RUNBOOK.md`, not copied.

## CLAUDE.md (proposal-only — not applied)

`CLAUDE.md` was **not** edited. Proposed one line to add immediately after the existing Changelog filenames paragraph (around lines 52–58):

At session start, run `python scripts/write_handoff_status.py` and read `HANDOFF_STATUS.md` for current CHANGELOG/TODO/orphan/persistence state; do not treat GROK_STATUS.md or dated docs/LOCAL_AGENT_CURRENT_HANDOFF_*.md as the live snapshot.

## Why

Session start needed one command that rebuilds a live snapshot from CHANGELOG + TODO + documented leftovers, instead of another dated handoff markdown or treating `GROK_STATUS.md` as current.

## Evidence

Successful run from the repository root with system Python 3.12.10 (not the farm venv):

```
A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe scripts\write_handoff_status.py
```

Exit code 0. Printed the path to `HANDOFF_STATUS.md`. File contained four sections, both same-day `2026-09-03h` changelogs, 37 open TODO checkbox lines, and the six seeded orphans. Regenerated once after this changelog so the recent list includes `2026-09-03j`.

## Files

- `scripts/write_handoff_status.py` (new)
- `HANDOFF_STATUS.md` (generated, overwritten)
- `CHANGELOG/2026-09-03j_handoff_status_generator.md` (this entry)

## Still unverified

Nothing in the generator live-probes farm/WireGuard/Celery state; those rows remain documented-seed only.
