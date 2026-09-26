# 2026-09-05an — Edge overlay up, gateway listening, token issued (no phone run)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05an**.

## Overlay (G1)

`WireGuardTunnel$edge-phone` is Running. Interface `edge-phone` has
`10.90.91.1/30`. Peer AllowedIPs in the workstation conf is
`10.90.91.2/32` only. Farm `WireGuardTunnel$hub` still Running at
`10.90.90.1/28`. `hub.conf` SHA-256 unchanged
`0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC`.
Mac WG was not edited. First UAC prompt was canceled; install succeeded
via `Desktop\Install-EdgePhoneOverlay.bat` (isolated installer, not the
farm hub installer).

## Listeners (G4)

Gateway PID 46176 `--listen`:

| Bind | Port | Evidence |
|---|---|---|
| `10.90.91.1` | 8743 | `Get-NetTCPConnection` Listen, `connect_ex=0` |
| `127.0.0.1` | 8744 | same |
| `0.0.0.0:8743` | — | `connect_ex=10049` (not bound) |

No job was injected (G6). Termux `--gateway` was not run (G10).

## Token (G5)

`POST http://127.0.0.1:8744/v1/admin/devices` `{device_id: pixel1}` → 201
`delivery=usb_adb_only`. Ledger capabilities `["edge_text_inference"]`
only; token stored as SHA-256 not plaintext; 0 jobs. Payload locked
SYSTEM+rhine on
`local_agent/edge_gateway/runtime/usb_adb_payload/` (edge-token + mTLS
PEMs). USB/ADB push **did not happen**: `adb devices` listed none.
No over-the-air copy.

Token SHA-256 `74f4303021b46a9e02985d4d18ac11e8e8be806e76169d1dc992811f7b51c699`
(length 43).
