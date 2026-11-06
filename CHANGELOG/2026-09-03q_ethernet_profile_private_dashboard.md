# 2026-09-03q — Ethernet network profile flipped to Private (Farm Dashboard LAN)

Windows network change on DuranGamingPC. Hub NIC left Public. No Redis/ACL change.

## What

`Ethernet` (`192.168.50.208`, profile name "We Don't Have Internet") was **Public**, so inbound rule `FarmDashboard TCP 8765 Private` (Private + LocalSubnet) never applied. Phone on home Wi-Fi could not load `http://192.168.50.208:8765/`.

Elevated: `Set-NetConnectionProfile -InterfaceAlias Ethernet -NetworkCategory Private`.
Confirmed `Get-NetConnectionProfile`: Ethernet **Private**, hub still **Public**.

## LAN retest

Mac `192.168.50.8` via `10.90.90.2` SSH: `curl http://192.168.50.208:8765/` returned **HTTP 200** Farm Monitor HTML. Dashboard still LISTENING `192.168.50.208:8765` PID 32652 (`dashboard\server.py`). Phone load still needs Rhine to try from the handset.

## Side effect: other Private-only inbound allow rules now apply on Ethernet

Intended: FarmDashboard TCP 8765.
Also now matching this NIC (Private-only, not already Public):
- Network Discovery (LLMNR 5355, NB 137/138, SSDP 1900, UPnP 2869, WSD 3702/5357/5358)
- Cast to Device / DIAL (TCP 10246/10247, RTSP 23554-23556, RTCP UDP)
- mDNS UDP 5353
- BambuStudio TCP/UDP Any
- Codex TCP/UDP Any
- Captain Hardcore TCP/UDP Any
- store app `ms-resource:ProductPkgDisplayName` TCP/UDP 7000

`Domain, Private` rules (AllJoyn 9955, Connected Devices Platform, Remote Assistance, some UWP) also start applying. Hub NIC unchanged (still Public).
