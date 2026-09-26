# 2026-09-05ad — PowerInfer-2 edge gateway v1 (server-only)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05ad**.

Parent: `CHANGELOG/2026-09-05w_powerinfer2_edge_gateway_scope.md`.
G1–G10 accepted in the build prompt.

## What shipped

Workstation SQLite gateway, own package, default off:

`local_agent/edge_gateway/` (`server.py`, `ledger.py`, `tlsutil.py`,
`logutil.py`, `Generate-EdgePhoneOverlay.ps1`).

| Bind | Address | Port (G4) |
|---|---|---|
| Phone API, HTTPS + mTLS | `10.90.91.1` | **8743** |
| Admin HTTP | `127.0.0.1` | **8744** |

Contract paths match the inert Termux client: `POST /v1/edge/jobs/claim`
and `POST /v1/edge/jobs/{id}/complete`. Caps re-enforced on the server
(12 000 / 512 / 16 000). One lease per device; idempotent complete (first
result wins, 409 on mutation); revoke expires the lease and complete is
401. Results stored as `untrusted`. Logs are ids/sizes only.

G3 grep-lock: production sources contain none of `FARM_BROKER_URL`,
`REDIS_PASSWORD`, `celery_app`, `load_dotenv`, `worker_farm`, etc.
Importing the server in a clean interpreter does not load celery/redis.

G1 overlay generator writes `runtime/wireguard/edge-phone.conf` +
`pixel.conf` (gitignored). **Did not** `-Install`, **did not** edit
`worker_farm/wireguard/hub.conf` or any Mac config.

G10: Termux worker not started, `--gateway` not used.

## Tests

```
python -m unittest local_agent.edge_gateway.test_edge_gateway -v
  Ran 19 tests in ~7s
  OK
python -m unittest local_agent.worker_farm.test_termux_powerinfer2_edge_worker -v
  Ran 3 tests
  OK
```

`--listen` without `10.90.91.1` on an interface: `WinError 10049`, exit 2,
no `0.0.0.0` fallback. After that attempt, 8743/8744 were not listening
(`connect_ex` 10061).

## Not done

Pixel `--once`, overlay install, USB/ADB token copy, farm Redis hop.
