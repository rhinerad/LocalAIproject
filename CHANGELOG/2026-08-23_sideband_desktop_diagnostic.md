# Sideband Desktop Diagnostic — 2026-08-23

- Installed the official Sideband 2.0.1 Windows package as an isolated desktop diagnostic application under `local_agent/vendor_sideband_desktop/`.
- Added `local_agent/LAUNCH_SIDEBAND_DESKTOP_DIAGNOSTIC.cmd`. It gives the desktop application separate Sideband and Reticulum configuration directories, so it cannot reuse the Equal Shares LXMF bridge identity or alter its configuration.
- The launcher refuses to open while `lxmf_agent.py` is running. A single workstation RNode Bluetooth/serial link must be owned by exactly one process, so the desktop app is for configuring and testing the PC node while the bridge is stopped.
- No radio settings, identities, bridge configuration, pipeline, or render process were changed.

## BLE RNode preflight

- Fixed the diagnostic Sideband profile to use separate local Reticulum ports and no AutoInterface. It now starts alongside the existing bridge without competing for Windows IPv6 multicast sockets.
- Identified the actual workstation-side BLE radio as `RNode 3B90` (`3C:0F:02:EC:0A:65`), and the second advertising RNode as `RNode B8EE`. The previously tested COM ports belong to Bluetooth audio devices, not either RNode.
- Installed `bleak` 3.0.2 in the bridge's Python runtime, then added `local_agent/probe_rnode_ble.py`. The preflight scans only for the official RNode Nordic-UART BLE service and sends no radio configuration or traffic.
- Current verified state: `RNode 3B90` is advertising the RNode UART service, but Windows does not expose it as a paired BLE GATT device. The preflight reports this explicitly and refuses to send even read-only RNode KISS queries until pairing is completed.
- No LoRa frequency, bandwidth, spreading factor, coding rate, transmit power, firmware, route, bridge identity, render, or pipeline setting was changed.

## USB workstation RNode verification

- The workstation RNode is now connected directly over USB as `COM11`. USB is the preferred host-to-radio link for the always-on workstation; the LoRa link to the phone-side node remains wireless.
- Read-only RNode KISS probing confirmed firmware `1.86`.
- Read-only `rnodeconf --info` identified the board as `Heltec LoRa32 v3` with an `SX1262` modem, supported range `850–950 MHz`, maximum `22 dBm`, and normal host-controlled mode. `--config` confirms Bluetooth enabled and Wi-Fi disabled.
- The board has no stored TNC radio profile, so a bridge configuration must provide the agreed frequency, bandwidth, spreading factor, coding rate, and transmit power. Those values were not guessed or written.
- `rnodeconf` reports a valid EEPROM checksum but an unverified firmware signature. No reflash, bootstrap, key change, or other hardware mutation was performed. Reflashing requires an explicit operator decision because it overwrites firmware.

## Matched phone-side radio profile

- The operator supplied a Sideband RNode screenshot for phone-side node `B8EE`. Its active profile is `914.875 MHz`, `500 kHz` bandwidth, `10 dBm` transmit power, spreading factor `7`, and coding rate `5`.
- Added a disabled-until-next-bridge-start `RNodeInterface` entry for the USB workstation node on `COM11` to `local_agent/rns_wifi/config`, using those exact values. Reticulum applies this profile only in volatile radio runtime when the bridge starts; it does not flash or otherwise persist a setting to the RNode.
- The existing bridge was not interrupted. Restarting it once is required to activate the USB/LoRa interface, after which the phone can be tested in airplane mode with Bluetooth connected to `B8EE`.

## Phone-side RNode connection confirmed in Sideband

- Sideband now shows `Connect using Bluetooth` and `Device requires BLE` enabled, with `RNode B8EE` selected as the preferred paired device. This is the required phone-side pairing/connection configuration for the advertised BLE RNode.
- Re-enabled the matching `COM11` workstation interface. It remains inactive until the existing bridge is restarted; no second bridge or radio owner was started.

## Reliable bridge launcher

- Added `local_agent/START_SIDEBAND_BRIDGE.cmd`, which runs the PowerShell bridge script with its folder context intact. This prevents the empty `$PSScriptRoot` failure caused by opening or pasting the `.ps1` script in an interactive PowerShell prompt.
- The PowerShell script now exits immediately with a clear instruction when invoked without a script location, rather than proceeding with blank paths and falsely appearing to start the bridge.
