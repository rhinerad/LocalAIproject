# 2026-09-05cs — G10 full phone-side setup authorized

## Scope

Operator tracking entry, dispatches the real Pixel setup.

## Context

`2026-09-05cm`/`cr` correctly stopped G10 twice: the Pixel was never
joined to the `edge-phone` WireGuard overlay (no `10.90.91.2`, no
official WireGuard app, 100% ping loss to `10.90.91.1`), and Termux only
has the token — no mTLS client certs, no worker script, no `llama-cli`,
no model. Pink did not fall back to plain Wi-Fi/Tailscale/ProtonVPN and
did not disable mTLS or install WireGuard without operator go-ahead.

## Operator decision

Operator authorized the full remaining phone-side setup: install
official WireGuard for Android, join the `edge-phone` overlay as
`10.90.91.2`, transfer the mTLS client certificate/key to Termux
(app-private storage, same pattern as the token), place the worker
script (`termux_powerinfer2_edge_worker.py`), `llama-cli`, and a model
onto the phone, then attempt the real G10 `--once` claim.

## Status

Dispatching Pink now.
