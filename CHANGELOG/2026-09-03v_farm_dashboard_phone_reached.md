# 2026-09-03v — Farm Dashboard reachable from Pixel on LAN

Follow-up to `2026-09-03q` (Ethernet Public -> Private).

Operator confirmed the Pixel 10 at `192.168.50.80/24` (Wi-Fi 6, gateway `192.168.50.1`) loaded `http://192.168.50.208:8765/`.

Guest-subnet and AP isolation were already ruled out (same /24, ping 4/4, ARP, Mac HTTP 200). Use `http://` not `https://`.
Hub NIC left Public.
