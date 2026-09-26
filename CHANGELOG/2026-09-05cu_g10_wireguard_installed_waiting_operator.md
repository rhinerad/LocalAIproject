# 2026-09-05cu — G10: official WireGuard installed; overlay wait on operator taps

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cu**.

Operator authorized remaining phone-side G10 setup. Stopped at actions
only the operator can complete. No admin inject. No `--once`. Farm
`hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

## 1. Install method

**ADB sideload of the official APK**, not Play Store.

- Why: Play Store install needs an on-phone Install tap. `adb install`
  of the project APK from `https://download.wireguard.com/android-client/`
  succeeded with no dialog (`Success`).
- File: `artifacts/wireguard_android/com.wireguard.android-1.0.20260315.apk`
- SHA-256 `F92971BC804F4C448E8845AE97E426095EAB06EC09A2473A3FA2CFE7288E3298`
  (16 943 472 bytes)
- `aapt dump badging`: `name='com.wireguard.android'`
  `versionName='1.0.20260315'` `versionCode='519'`
- On device: `pm path com.wireguard.android` present;
  `dumpsys` `versionName=1.0.20260315` `installerPackageName=null`

Not used: Play Store, F-Droid mirrors, APKPure, Tailscale, ProtonVPN.

## 2. Overlay config (keys unchanged; hub not touched)

Workstation `WireGuardTunnel$edge-phone` still Running at `10.90.91.1/30`,
UDP `51821` listening on `0.0.0.0` / `::`. Phone `pixel.conf` still has
Address `10.90.91.2/30`, AllowedIPs `10.90.91.1/32`, same keys/peer
public key. **Only Endpoint was corrected:** generator had
`10.90.91.1:51821` (cannot establish a tunnel). Now
`192.168.50.208:51821` (workstation Ethernet, same `/24` as Pixel
`wlan0 192.168.50.80`). That is WireGuard **underlay** UDP, not a
substitute for overlay HTTPS to `10.90.91.1:8743`.

Staged USB/ADB (hash-only):
`9b40f3083d166f67dfee19c078bed0c2e655d283f4d87b5b65aab92956a0fe41`
matches host `pixel.conf` at
`/sdcard/Download/edge-phone-pixel.conf` and
`/sdcard/Android/data/com.wireguard.android/files/edge-phone-pixel.conf`.
App launched: `am start com.wireguard.android/.activity.MainActivity`.

This APK does **not** export a VIEW `.conf` importer.
`SET_TUNNEL_UP` requires `com.wireguard.android.permission.CONTROL_TUNNELS`.
`VpnService` is not grantable from ADB on this non-rooted Pixel without
the system “Connection request” dialog. Did not `appops`/`input tap`
around that.

## 3. Not done (blocked)

- Pixel still has **no** `10.90.91.2`. Overlay ping not re-tried as a
  substitute path.
- Inbound UDP **51821** has no firewall rule yet (hub’s 51820 rule
  exists and was not edited). `New-NetFirewallRule` Access denied
  without elevation. Bat:
  `Desktop\Install-EdgePhoneUdpFirewall.bat` (UAC). Script:
  `local_agent/edge_gateway/Install-EdgePhoneUdpFirewall.ps1`.
- mTLS PEMs not copied into Termux home. Worker / `llama-cli` / model
  not transferred. Worker client-cert TLS not added. No job injected.

Did not fall back to Wi-Fi HTTPS, Tailscale, or ProtonVPN, and did not
disable mTLS. G10 still open.
