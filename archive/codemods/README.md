# One-shot codemods (archived 2026-11-06)

These scripts were in-place patchers used once during September 2026 sessions
(`_patch_*`, `_fix_*`, `fix_*`, `patch_*`, `_astra_*`, `_verify_*`,
`_recompile_*`). Nothing in the live tree imports them; several were applied
twice and left duplicated conditions in `batch_run_backrooms_gvd.py` and
`generate_video.py` (cleaned up in the same remediation). They are kept here as
evidence of what was changed and must not be re-run against the current tree.
