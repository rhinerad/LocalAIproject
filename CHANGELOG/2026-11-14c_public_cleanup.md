# 2026-11-14c — Clean the public repo: private data out, SOC items out

## Why

The repository is public and is linked from the operator's resume. It still
tracked private data that `CLAUDE.md` §7 says is never committed, and it held
home-SOC material that now lives in its own repo
([Home-SOC-](https://github.com/rhinerad/Home-SOC-)).

## What changed

- **Untracked 526 files**, the same list as `scripts/untrack_private_data.ps1`
  plus two extras: `local_agent/chats/` (150), `local_agent/uploads/` (28),
  `local_agent/render_jobs/` (26), `logs/` and every tracked `*.log`/`*.err`,
  `ARCHIVE_DECISION.md`, `.claude/settings.local.json`, `.claude/launch.json`,
  `CHANGELOG/.id_claims/`, and `powerinfer_project/approved_tasks.jsonl` (the
  explicit-content eval set, audit P0 #2, now also in `.gitignore`).
- **SOC items removed**: the home-lab section of `README.md`, and
  `docs/visuals/home-lab-map.gif` with its HTML source.
- **Personal names replaced** in 64 files (mostly changelog notes):
  `Louises-MBP` / `Louises-MacBook-Pro` → `Mac-Worker` / `mac-worker`, the Mac
  login → `user@`, "Louise's Mac" → "the Mac worker". The dashboard's worker
  regex is now `(?:MBP|Mac|Worker)` and still matches the live
  `celery@Louises-MBP` name through `MBP`.
- Left as is: `local_agent/worker_farm/Lock-Phase1SecretFile.ps1` matches the
  `tiffa` account by name when checking ACLs. Changing it would change what the
  script checks on the workstation.

## Evidence

`local_agent/worker_farm` and `test_farm_offload.py`: 178 passed, 9 failed,
and the 9 failures are identical before and after the rename (Windows-only
tunnel and ACL tests). Secret scan of the tracked tree finds only the
deliberately fake tokens in `test_farm_core.py`.

## Before the workstation syncs this (important)

As with 2026-11-14b: a plain merge of `main` on the workstation deletes files
that `main` no longer tracks. That now includes **your chats, uploads and
render jobs**. Run `scripts/untrack_private_data.ps1` in the workstation
checkout and commit **before** merging `main`, or back up `local_agent/chats`,
`local_agent/uploads`, `local_agent/render_jobs` and `logs` first.

Still open (operator): these files remain in older commits and on the older
`claude/*` branches. Only a history rewrite removes them from GitHub, and the
Reticulum identity that was committed should be rotated either way.
