# 2026-08-26 — Sideband RNode startup fallback

- Fixed `START_SIDEBAND_BRIDGE.ps1` readiness delay and corrected its RNode
  configuration-file check.
- When Windows cannot present/execute the optional administrator firewall step,
  the launcher now starts the configured USB RNode transport instead of blocking
  all paired-phone messaging. It warns that Wi-Fi/TCP inbound fallback remains
  unavailable until the firewall rule is installed.
- Verified live bridge process binds Reticulum TCP fallback on
  `192.168.50.208:4242`; localhost agent remains private on `127.0.0.1:8760`.
