# 2026-09-05cr — G10 Pixel --once still blocked after Allow (no overlay)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cr**.

Operator tapped USB debugging Allow. ADB is `device`
(`5A080DLCH0034F`, Pixel 10 Pro `blazer`). First `--once` was **not**
started. No admin inject. Farm `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

## Preconditions that held

- `WireGuardTunnel$edge-phone` Running, `10.90.91.1/30`
- Gateway PID 46176 Listen `10.90.91.1:8743` and `127.0.0.1:8744`
- `pixel1` row not revoked, capabilities `["edge_text_inference"]`,
  distinct from `ws-indep-1`
- Termux `~/.config/local-agent/edge-token` SHA-256
  `74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`
  (len 43; DocumentsProvider read, hash only)

## Why it stopped (same as 2026-09-05cm; Allow only unblocked ADB)

The Pixel still has **no** `10.90.91.2` address. `pm path
com.wireguard.android` is empty. Installed VPN-related packages include
Termux, Tailscale (`com.tailscale.ipn`), and ProtonVPN
(`ch.protonvpn.android`) — not official WireGuard. `ping -c 3 10.90.91.1`
is **100% loss**. Phone LAN remains `wlan0 192.168.50.80/24`.

Termux `~/.config/local-agent/` still has **only** `edge-token` (no mTLS
PEMs). Staging PEMs remain in Android/data and `/data/local/tmp`. The
inert worker still has no client-cert TLS (`ssl` / `load_cert_chain`
absent). Worker script, `llama-cli`, and model are not in Termux home.

Did not fall back to Wi-Fi `192.168.50.80`, Tailscale, or ProtonVPN, and
did not disable mTLS. Did not install WireGuard without operator
go-ahead. G10 still open.
