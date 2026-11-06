# 2026-09-05cg — G10 Pixel --once not run (ADB unauthorized)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cg**.

G10 was operator-authorized. The first real Pixel `--once` was **not**
executed. No admin inject, no Termux worker, no farm files touched.

## Preconditions (actual)

| Item | Value |
|---|---|
| `WireGuardTunnel$edge-phone` | Running, `10.90.91.1/30` |
| Gateway PID 46176 | Listen `10.90.91.1:8743` and `127.0.0.1:8744` |
| `pixel1` row | capabilities `["edge_text_inference"]`, not revoked; `token_hash` prefix `74f4303021b46a9e` matches known token SHA-256; distinct from `ws-indep-1` |
| Phone token file | **not re-read** this session |
| ADB | Pixel 10 Pro USB present (`VID_18D1`, serial `5A080DLCH0034F`) but `unauthorized` for ~2 minutes of polling |
| `hub.conf` SHA-256 | unchanged `0EA2DF795F5FA8344CDE522FBEC9B22FC3EAA52A2918A724863A4D5B57FC13BC` |

Did not inject a queued job while the phone could not claim. G10 remains
open. Tap **Allow USB debugging** on the Pixel and re-run.
