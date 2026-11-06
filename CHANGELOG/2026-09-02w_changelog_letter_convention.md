# 2026-09-02w — changelog letter allocation for parallel agents

## What

`2026-09-02u_farm_status_daemon.md` was renamed to `2026-09-02v_farm_status_daemon.md` so it no longer collides with `2026-09-02u_compaction_prefetch.md` (two agents independently chose `u` the same day). First-come kept `u`.

## Convention

Changelog entries are `YYYY-MM-DDx_description.md` with a sequential letter `x`. Before naming one, check `CHANGELOG/` for today's date (or run `python scripts/next_changelog_id.py`) instead of guessing. Documented in `CLAUDE.md` under the existing `CHANGELOG/` paragraph so every agent sees it at session start.

## Files

- `CHANGELOG/2026-09-02v_farm_status_daemon.md` (renamed from `u_`)
- `scripts/next_changelog_id.py` (new)
- `CLAUDE.md` (filename convention note)
- `TODO.md` (reference to the renamed entry)
