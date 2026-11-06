# Sideband direct-LAN fallback — 2026-08-23

## Why

The workstation's LXMF AutoInterface was confirmed running on both active
adapters and its scoped Windows firewall rules were confirmed active for both
Private and Public profiles. The phone's Sideband Announce Stream still received
no workstation announcement. This is consistent with a router blocking the
IPv6 multicast AutoInterface uses between Wi-Fi and Ethernet clients.

## Change

`local_agent/rns_wifi/config` now adds `Equal Shares Direct LAN`, a
`TCPServerInterface` bound specifically to the workstation Ethernet adapter on
port 4242. It transports Reticulum/LXMF only. The HTTP GUI remains exclusively
on `127.0.0.1`.

`ENABLE_SIDEBAND_WIFI_FIREWALL.ps1` adds a separate inbound TCP rule for that
port, restricted to `LocalSubnet`, the selected Python executable, and the
Private/Public Windows network profiles. The launcher validates both the
AutoInterface and direct-LAN rules before it starts the bridge.

The bridge Reticulum profile now sets `enable_transport = Yes`. A TCP server
needs transport enabled to pass announcements and routes between its connected
Sideband TCP clients and the workstation's own LXMF destination. This is
Reticulum packet routing only; it is not an HTTP listener and does not alter the
per-identity permission gate.

The direct-LAN TCP rule is scoped to port 4242 and `LocalSubnet`, but is no
longer tied to an individual Python executable path. The bridge can be started
by a different local Windows account; binding it to the first account's Python
path caused the real bridge process to be silently blocked. This change does
not open HTTP and does not permit a different port or remote subnet.

## Safeguards unchanged

The remote side remains LXMF only; no HTTP LAN bind was introduced. Identity
pairing, default denial for write/build/render tools, and remote audit logging
are unchanged.
