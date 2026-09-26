# 2026-08-23 — Sideband bridge over workstation Wi-Fi

## What changed

- Added a dedicated Reticulum AutoInterface profile at
  `local_agent/rns_wifi/config`.
- Pinned the profile to the active Qualcomm Wi-Fi interface that owns
  `192.168.50.81`, excluding Ethernet and inactive virtual Wi-Fi adapters.
- Updated `START_SIDEBAND_BRIDGE.ps1` to always pass that profile to the LXMF
  bridge.
- Added a one-time elevated firewall helper. It allows only UDP 29716/29717/42671,
  only for the selected Python executable, only on Private networks, and only
  from the local subnet. The launcher invokes it only when its named rule is absent.
- Documented the same-Wi-Fi setup and the adapter replacement caveat.
- Added `START_PHONE_AGENT_WIFI.cmd` to the desktop Equal Shares launcher folder.
  It starts the normal localhost agent when needed and then starts the opt-in Wi-Fi
  bridge; it does not start ComfyUI or any render queue.
- Made the desktop starter elevate itself before setup. This keeps the one-time
  firewall installation and the long-running bridge in the same visible window,
  instead of letting a failed nested elevation close the starter silently.
- Corrected the rule to include AutoInterface's separate unicast discovery port
  `29717`. The helper now repairs an existing named rule instead of treating mere
  existence as sufficient, and the launcher verifies all three required ports.
- Added IPv6 link-local (`fe80::/10`) as a permitted remote range. Reticulum
  AutoInterface uses link-local IPv6 for Wi-Fi discovery; this range cannot route
  beyond the local link and remains constrained to the Python executable, Private
  networks, and the three Reticulum UDP ports.
- Updated the starter's rule-health check to require both local-subnet and IPv6
  link-local coverage, so an older partially configured named rule is repaired on
  the next normal launch.
- The bridge now re-announces its LXMF delivery destination every 30 seconds.
  This lets a Sideband client that joins the Wi-Fi network after the bridge starts
  resolve the agent address without waiting for a manual bridge restart. These
  announcements carry no chat content.
- The AutoInterface profile now uses both active private-LAN adapters: the
  Realtek Ethernet controller (workstation address `192.168.50.208`) and the
  Qualcomm Wi-Fi adapter (`192.168.50.81`). This avoids relying on cross-media
  multicast forwarding when the workstation is wired and the phone is wireless.
- Corrected the Windows AutoInterface adapter syntax so Reticulum receives the
  brace-wrapped adapter IDs it uses internally; the entries are quoted only to
  keep ConfigObj from mistaking the braces for list syntax.
- Corrected the firewall profile mismatch found during a live phone test: this
  workstation marks its active Ethernet and Wi-Fi networks as Public. The named
  rule now covers Private and Public profiles, while remaining constrained to
  the bridge Python executable, UDP 29716/29717/42671, local-subnet peers, and
  IPv6 link-local peers. It does not expose the localhost web agent.

## Safeguards preserved

- The local web application still binds only to `127.0.0.1:8760`; HTTP is not
  reachable from the LAN.
- Only the LXMF/Reticulum transport uses Wi-Fi.
- Pairing, per-identity remote permissions, tool auditing, and the tool whitelist
  are unchanged.
- The Equal Shares render pipeline and ComfyUI port 8188 were not started.

## Verification

- Live Reticulum initialization adopted only
  `{7BD5276E-53B8-48F6-B354-8F4F6E105C4A}`, the adapter with IPv4
  `192.168.50.81`, and retained LXMF address
  `2adc394dd3e580e4965aa88aa7b67cc4`.
- LXMF/security tests: 8/8 passed.
- Native function calling: 9/9 passed; media analysis: 9/9 passed; dynamic model
  routing: 13/13 passed.
- H3 prompt validation: 124/124 valid.
- Port 8188 remained closed and the local web app remained revision r9 on
  `127.0.0.1:8760`.
