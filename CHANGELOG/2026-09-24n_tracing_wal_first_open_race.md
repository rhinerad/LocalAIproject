# 2026-09-24n — tracing: WAL first-open race no longer disables tracing

Found while verifying `2026-09-24l`. `test_tracing.TracingTests.test_concurrency_two_threads`
failed intermittently (`AssertionError: 6 != 1`): in two consecutive full
non-live suite runs, and 1 in 6 runs of `python -m unittest test_tracing` alone.

Backups: `local_agent/tracing.py.bak_wal_race_20260924T105158`,
`local_agent/test_tracing.py.bak_wal_race_20260924T105158`.

No ComfyUI, no GPU. Unit tests only.

## Cause (measured, not inferred)

A harness wrapped `tracing._mark_broken` to record its exception and ran the
two-thread turn→hop→reason scenario against a fresh DB each time:
**29 of 200 runs failed**. Every failure was
`sqlite3.OperationalError: database is locked`, always raised at
`PRAGMA journal_mode=WAL` in `tracing._connection()`.

On a brand-new DB that pragma converts rollback-journal mode to WAL. The
conversion needs an exclusive lock, and SQLite reports "locked" immediately
to the losing connection instead of waiting out the 10 s busy timeout.
`span()` caught it and `_mark_broken()` set `_BROKEN` (OperationalError is a
DatabaseError). After that, `enabled()` returned False for the rest of the
process and every later span was a dummy.

Production impact: the first time two threads opened a new `knowledge/traces.db`
at once, tracing could silently switch itself off until the process restarted.

## Change — `local_agent/tracing.py` (LF)

New `_enable_wal(conn)`, called from `_connection()` in place of the bare pragma:
- The pragma runs under a module-level `_WAL_LOCK` (`threading.Lock`), which
  serializes the conversion within the process. On an existing WAL DB it is a
  no-op read, so the lock is held only briefly.
- On `OperationalError` containing "locked"/"busy" it retries up to
  `_WAL_RETRIES = 50` times, `_WAL_RETRY_SLEEP = 0.02` s apart (~1 s). This
  covers a second process creating the DB at the same moment. Other errors, or
  the last failed attempt, raise as before, so a genuinely broken DB still
  marks tracing broken.
- "Tracing never raises into the caller" is unchanged.

## Verification

- Same harness after the fix: **0 of 1000** runs failed (before: 29/200).
- New `test_tracing.TracingTests.test_concurrent_first_open_never_marks_broken`:
  25 rounds, each on a fresh DB with 4 threads. It asserts `_BROKEN` stays
  False, 4 spans per DB, and journal mode `wal`. Against the pre-change
  `tracing.py` (temp copy) it fails in round 0 with `database is locked`.
- `python -m unittest test_tracing`: 16 OK, **30/30** consecutive runs clean.
- Full non-live suite from `local_agent/`:
  `python -m unittest $(ls test_*.py | grep -v _live | sed 's/\.py$//')` →
  **1466 tests OK (2 skipped)**. That is 1460 from `2026-09-24l` + this test
  + 5 tests another agent added in parallel (`bak_labelecho_20260924T105305`).
