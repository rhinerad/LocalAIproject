# Sideband live pairing and launcher hardening — 2026-08-23

## Live acceptance

A stock Sideband phone completed a real LXMF turn through the workstation bridge.
The bridge received the phone's verified LXMF delivery address, the operator
explicitly paired that address, and the accepted turn created the normal
persistent local-agent conversation with every message marked `source: phone`.
The desktop GUI and its localhost-only HTTP binding were unchanged.

## Correct pairing flow

The public identity material initially supplied by Sideband did not equal the
sender's LXMF delivery destination used for the message. To avoid guessing or
auto-approving an unknown identity, refused first-contact messages now append
only their verified 32-character delivery address and request ID to
`runtime/lxmf/unpaired_attempts.jsonl`. No untrusted message content is stored.
The operator then pairs that exact address using `remote_security.py`.

## Network hardening

The live home-LAN path is restricted to a phone-only TCP/4242 firewall rule.
`START_SIDEBAND_BRIDGE.ps1` now recognizes this more restrictive rule and does
not repeatedly request elevation to convert it to a broader local-subnet rule.
HTTP remains bound to `127.0.0.1`; remote write, build, memory, and render
capabilities remain default-denied per paired identity.

## Verification

- `python local_agent\\test_lxmf_bridge.py`: 8/8 passed.
- A real paired Sideband message created a persistent chat and received a reply.
- The paired phone has no granted privileged tools.
