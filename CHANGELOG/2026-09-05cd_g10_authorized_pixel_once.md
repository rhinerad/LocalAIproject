# 2026-09-05cd — G10 authorized: Pixel --once, first real run

## Scope

Operator tracking entry, dispatches the actual Pixel run.

## Context

`2026-09-05cb` (Task #66) proved G6-G9 on the workstation side only:
happy-path claim/complete, idempotent re-claim, replay rejection,
oversize rejection, revoked-token rejection, no phantom second job,
clean env/log audit — all against a synthetic `ws-indep-1` device, no
phone involved.

## Operator decision

Operator authorized G10: the real Pixel 10 Pro, running the actual
`termux_powerinfer2_edge_worker.py` in `--once` mode over the real
`edge-phone` overlay, using the token installed and hash-verified in
`2026-09-05bz`.

## Status

Dispatching Pink now to run G10 for real, one benign job only, then
report actual evidence (not "should work").
