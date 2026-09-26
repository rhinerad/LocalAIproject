# ADR 0001 — Localhost HTTP and paired LXMF transport

**Status:** Accepted

## Decision

Keep the desktop HTTP service bound to `127.0.0.1`. Remote phone access travels
through Reticulum/LXMF and requires a paired cryptographic identity.

## Why

The browser/API surface is not exposed to the LAN or public internet. LXMF
provides a separate message transport with a per-identity permission layer.
Remote identities default-deny state-changing and rendering tools, and their
tool calls are logged.

## Consequences

- The desktop GUI remains unchanged and local-only.
- A phone must pair before it can converse with the bridge.
- This is an experimental transport layer until end-to-end delivery metrics are
  collected; Bluetooth pairing is not proof of mesh delivery.

## Evidence

`local_agent/lxmf_agent.py`, `local_agent/test_lxmf_bridge.py`, and
`CHANGELOG/2026-08-25_sideband_sf12_bridge_recovery.md`.
