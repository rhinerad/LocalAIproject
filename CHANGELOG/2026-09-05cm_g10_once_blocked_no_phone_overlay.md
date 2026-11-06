# 2026-09-05cm — G10 Pixel --once stopped: phone has no overlay

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cm**.

ADB authorized (`5A080DLCH0034F device`, Pixel 10 Pro). First `--once`
was **not** started. No admin inject. Farm `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

## Preconditions that held

- `WireGuardTunnel$edge-phone` Running, `10.90.91.1/30`
- Gateway PID 46176 Listen `10.90.91.1:8743` and `127.0.0.1:8744`
- `pixel1` row not revoked, capabilities `["edge_text_inference"]`,
  distinct from `ws-indep-1`
- Termux `~/.config/local-agent/edge-token` SHA-256
  `74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`

## Why it stopped (differs from workstation G6–G9)

Workstation test ran **on the overlay host**. The Pixel has **no**
`10.90.91.2` address, no WireGuard package (`pm` shows Termux, Tailscale,
ProtonVPN — not `com.wireguard.android`), and `ping 10.90.91.1` is
**100% loss**. Also missing on Termux home: worker script, `llama-cli`,
model, mTLS PEMs (only `edge-token` in `~/.config/local-agent/`). The
inert worker still has no client-cert TLS, which would fail G2 even after
the overlay exists.

Did not fall back to Wi-Fi `192.168.50.80`, Tailscale, or ProtonVPN, and
did not disable mTLS. G10 still open.
