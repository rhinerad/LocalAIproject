# 2026-08-29 — Wired run_pipeline.ps1 to actually call vault.init_vault()

## What changed

`tools/powerinfer/run_pipeline.ps1` computed `$VaultRoot` from
`vault.default_vault_path()` and then joined bundle paths with raw
`Join-Path`/`New-Item` calls throughout every `Invoke-*` function. It never
called `vault.init_vault()`, `assert_outside_repo()`, or `preflight()` at
all — `TODO.md`'s own note already said as much ("not yet wired to fail
closed if this vault is uninitialized"), but the actual consequence is
broader than that phrasing suggests: on any machine without a `D:` drive
(confirmed true of the sandbox this session runs in, and possibly true of
others), `default_vault_path()`'s fallback is `REPO_ROOT/artifacts/
powerinfer_vault` — **inside the git tree** — and nothing stopped the
pipeline from writing GGUFs, activation tensors, and predictor mmaps there
with no `.gitignore` protecting them from `git add`.

Added `Invoke-VaultInit`, called once right after `-Stage show` returns (so
the zero-side-effect preview path is untouched), which shells out to
`vault.init_vault(Path($VaultRoot))` and throws with a clear message if it
refuses — which it will, on the in-repo fallback, unless `-Vault` or
`$env:POWERINFER_VAULT` is set explicitly.

## Why

Found while reviewing `run_pipeline.ps1` end to end to understand exactly
what `TODO.md`'s vault caveat meant, rather than taking the one-line note at
face value. This project's own standing rule elsewhere (`SOURCE_BACKUP_POLICY.md`,
the backup builder's exclusion list) treats "large binaries or secrets landing
in the git tree" as a real, specifically-guarded-against failure mode; this
was a live path to exactly that on any machine without the preferred drive.

## Verification

- Reran `python -m unittest test_powerinfer_pipeline -v` after the edit
  (unaffected — the test file doesn't exercise `run_pipeline.ps1`): 18/18.
- Directly exercised the exact command `Invoke-VaultInit` runs, in isolation,
  against an isolated copy of `vault.py`/`pipeline_lib.py`:
  - `init_vault(Path('<repo>/artifacts/powerinfer_vault'))` (the in-repo
    fallback) raised `VaultError` with the expected message.
  - `init_vault(Path('/tmp/.../outside_vault'))` (an explicit outside path)
    succeeded, created `production/quarantine/scratch/private/keys`,
    `.gitignore`, and `vault.json` as expected.
- The PowerShell wrapper itself (`Invoke-VaultInit`'s `& $Py -c "..."` call,
  its `$LASTEXITCODE` check, and the call site right after `-Stage show`)
  was not run — no `pwsh` in this sandbox, same limitation as the earlier
  `-VramBudget` fix. Read through twice for the backtick escaping in the
  throw message (`` `n `` for newline, `` `$env:POWERINFER_VAULT `` to print
  the variable name rather than expand it).

## Deliberately not done

Did not route the per-stage directory creation (`Invoke-Intake`,
`Invoke-Calib`, `Invoke-Convert`, etc.) through `vault.create_bundle()` /
`vault.bundle_paths()` — that would replace several already-working,
individually Force-gated overwrite checks scattered through the script with
a single shared one, which is a larger and riskier rewrite of a file another
session is actively iterating on. The narrower fix (call `init_vault` once,
up front) closes the actual safety gap — in-repo writes with no
`.gitignore` — without touching the rest of the stage logic. Flagging the
bundle-creation consolidation as a reasonable follow-up, not doing it now.

## What is unverified

Whether `run_pipeline.ps1` actually refuses cleanly end-to-end on a real
Windows machine with no `D:` drive, and proceeds cleanly on one that has it
or an explicit `-Vault`. Needs a `pwsh` run to confirm; the Python-level
behavior it depends on is proven above.
