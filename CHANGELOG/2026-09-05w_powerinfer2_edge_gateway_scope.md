# 2026-09-05w — PowerInfer-2 edge gateway: scope only

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05w**.

Task #50. Design note only — no listener, no WireGuard peer, no token
file, no farm `.env` read, no Pixel contact.

Doc: `docs/design_notes/POWERINFER2_EDGE_GATEWAY_2026-09-05.md`.

## Finding

Phase D is blocked on a workstation gateway that does not exist. The
Termux client contract already speaks `POST /v1/edge/jobs/claim` and
`…/complete`, HTTPS-only, non-loopback, `edge_text_inference`, 12 000-char
prompt, 512-token cap. Those paths 404 until this service is built.

MVP: process on DuranGamingPC only; phone API bound to a **new** overlay
(`/30`, recommended `10.90.91.0/30`), not farm `10.90.90.0/28`; admin on
`127.0.0.1`; SQLite ledger; no Redis/AES/Celery import. mTLS-capable;
whether it is on for the first listen is operator G2.

A lost phone with this gateway still sees the one queued prompt and can
lie about the result. It must not reach Redis, Celery, chat exports, or
the farm hub key. Putting the Pixel on `10.90.90.0/28` would make Redis
at `10.90.90.1:6379` a reachability problem — rejected for MVP.

Build is gated on operator sign-off G1–G10 in the design note (overlay,
mTLS, no farm `.env`, hostname/port, token ceremony, benign prompt,
result handling, revoke semantics, logs, Pixel `--once`).

No production code changed. Gateway TODO checkbox stays unchecked.
