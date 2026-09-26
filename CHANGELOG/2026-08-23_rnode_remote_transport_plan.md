# ESP32 LoRa V3 remote transport decision — 2026-08-23

## Operator decision

The paired ESP32 LoRa V3 boards are the preferred phone-to-workstation route
when the operator is away from the house. Each board is connected to its host
over Bluetooth. The local Wi-Fi/TCP Reticulum path remains the nearby-house
fallback.

## Safety and configuration gate

An ESP32 LoRa V3 board is not automatically a Reticulum RNode. Before adding a
workstation `RNodeInterface` or enabling the phone's Sideband RNode connection,
verify that both boards run compatible RNode firmware and deliberately record
the matching radio configuration: legal frequency, bandwidth, spreading factor,
coding rate, output power, and any interface network name/passphrase. The bridge
will not probe, flash, or overwrite either radio's configuration by guesswork.

## Network boundary

LoRa carries encrypted Reticulum/LXMF only. It does not change the agent web
server's `127.0.0.1` binding, the per-identity permission gate, render denial,
or remote-tool audit logging.
