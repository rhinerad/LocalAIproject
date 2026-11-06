# 2026-09-05dd — G10 overlay up; Termux inward copy + model still blocking --once

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05dd**.

No admin inject. No `--once`. Farm `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.

## Overlay (operator imported `pixel.conf`)

Pixel `tun0` is `10.90.91.2/30`. Workstation pings `10.90.91.2` 0%
loss (39–112 ms). Phone `ip route get 10.90.91.1` is `dev tun0 src
10.90.91.2`. Phone `toybox nc` to `10.90.91.1:8743` returns 7 bytes,
exit 0 (gateway TLS is reachable over the overlay).

Phone ICMP ping to `10.90.91.1` is still 100% loss: Windows has no
enabled inbound Echo Request rule (File and Printer Sharing ICMPv4-In
is off). Adding a scoped ICMP rule needs elevation; not done. Overlay
TCP to the gateway port is the G10 path.

Staged long-name `edge-phone-pixel.conf` was invalid (Android tunnel
name max 15). Restaged/imported as `pixel.conf`. Shared-storage copies
of that conf were deleted after import.

## Worker mTLS (host)

`termux_powerinfer2_edge_worker.py` now requires sibling
`ca.cert.pem` / `client.cert.pem` / `client.key.pem` and presents them
on HTTPS (TLSv1.2+, hostname check, `CERT_REQUIRED`). HTTPS /
non-loopback / kind allowlist / shell-free argv tests still pass
(`unittest` 4/4 in farm venv).

## Staged on Pixel (ADB → Termux Android/data, hashes match host)

`/sdcard/Android/data/com.termux/files/powerinfer-edge/` dir `711`:

| File | SHA-256 |
|---|---|
| `ca.cert.pem` | `b3ba33d94931e5a84134cd31e58b553291aaac55d056e86d5b8f9f399754c104` |
| `client.cert.pem` | `056402d04bcb419853b116ecd081c4c470d2ed8022a44758dd39dbe6a10b3d55` |
| `client.key.pem` | `d2c0e11d43b7f87d3f6cb4f3b4cc786ecd16718e0a9af2e63bac0742de12d62a` |
| `llama-cli` | `3b902e1c53f5a2c1c6c8fc1268dee0a0e09917cbe154cb006a007c8667ae8349` (pin) |
| `libaio.so.1` | `2b09131bb414b31e37cfb125054e94979c83b021f356576d246eeb9dbcca1f5f` (from `libaio.so.1.0.1`; Windows symlink unreadable) |
| `termux_powerinfer2_edge_worker.py` | `d56f80401a160ea2395a3ae218c8ee6f0605865a838393a7e2c9d2311693c8c0` |

Termux home still has **only** `edge-token` (DocumentsProvider cannot
write). Same inward `cp` as `2026-09-05bz` is required. No SmallThinker
GGUF exists on this host (`artifacts/powerinfer_vault` empty; none
fetched at cross-build). Did not download a model. Did not use Wi-Fi
HTTPS, Tailscale, or ProtonVPN. G10 still open.
