# Wall-clock metric (audit §12)

**Measure wall-clock per accepted second of video**, not per raw render second.

## Definition

```
wall_clock_per_accepted_second =
    total_operator_wall_clock_seconds
    / accepted_timeline_seconds
```

Where:

- `total_operator_wall_clock_seconds` includes queue wait, render, technical QA,
  content QA, retries, and continuity rebinds for shots that land in the cut.
- `accepted_timeline_seconds` is the sum of durations of **SELECTED** shots that
  ship in the editorial timeline (failed / discarded attempts do not add to the
  denominator).

## Why not raw render time

A fast first render that fails technical QA and is retried twice is slower in
practice than a slower first render that selects cleanly. Continuity invalidation
(parent re-select) also burns wall-clock that raw GPU timers miss.

## Helper (Python)

See `backend_profiles.wall_clock_per_accepted_second(total_wall_s, accepted_seconds)`.

## Starting profiles

JSON under this directory are **starting points only** — not measured guarantees
on RTX 5080. Record observed `wall_clock_per_accepted_second` alongside each
profile when live GPU benchmarks run.
