# Experimental RNode inventory (portfolio-safe)

**Status:** experimental mesh transport layer. Not a product claim.
**Source:** existing changelog and diagnostic notes. No radios were probed,
flashed, or reconfigured for this document.

This inventory is for evidence tracking. It omits COM ports, node names,
passphrases, paired identities, and any network keys.

## Hardware class

| Role | Board class recorded | Radio | Host link |
|---|---|---|---|
| Workstation | Heltec LoRa32 v3 | Semtech SX1262 | USB serial + Bluetooth to the host |
| Phone companion | ESP32 LoRa V3 class (LilyGO/Heltec family; phone-side exact SKU not independently re-verified here) | LoRa in the 850–950 MHz capable class | Bluetooth to the phone |

A board is not an RNode until compatible **RNode firmware** is present and a
deliberate radio profile is applied. The workstation diagnostic found **no
stored TNC radio profile**, so the bridge must supply the agreed values.

## Recorded radio profile (workstation, after SF12 update)

Values below are operating assumptions already written into project changelogs.
They are **not** a regulatory determination.

| Parameter | Recorded value | Notes |
|---|---|---|
| Frequency | 914.875 MHz | US 915 MHz ISM-class setting already in use |
| Bandwidth | 500 kHz | |
| Spreading factor | 12 | Updated 2026-08-25 from the earlier SF7 phone screenshot |
| Coding rate | 5 | |
| Transmit power | 10 dBm | Well below the SX1262 22 dBm maximum reported by `rnodeconf --info` |
| Wi-Fi on the radio | disabled | Host-controlled mode |
| Bluetooth on the radio | enabled | **Host-to-board cable replacement only** |

## What Bluetooth pairing is not

Bluetooth (or USB serial) only attaches the radio to its host. It does **not**
prove:

- Reticulum path establishment;
- LXMF delivery;
- encryption/identity pairing on the mesh;
- usable latency, loss, or range.

A stock-Sideband **LXMF round trip over the local Wi-Fi/TCP fallback** is a
separate, already-recorded desktop experiment. It is not LoRa mesh evidence.

## Legal / operating assumptions (unverified by counsel)

- Operate only on a frequency, bandwidth, and power the operator is allowed to
  use in their location.
- Do not raise TX power, change band, or flash firmware from an agent session
  without an explicit operator request.
- Treat all radio work as experimental until a controlled packet-delivery
  experiment exists. See `radio_packet_experiment.md`.

## Evidence links (private tree)

- `CHANGELOG/2026-08-23_rnode_remote_transport_plan.md`
- `CHANGELOG/2026-08-23_sideband_desktop_diagnostic.md`
- `CHANGELOG/2026-08-25_sideband_sf12_bridge_recovery.md`
- ADR 0001 (`docs/adr/0001-localhost-http-and-lxmf.md`)
