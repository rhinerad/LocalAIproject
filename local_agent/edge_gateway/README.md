# PowerInfer-2 edge gateway (workstation, Phase D v1)

Disabled unless `--listen`. Does not load farm broker config. Does not start
the Termux worker (G10).

## Binds (G1, G4)

| Surface | Address | Port |
|---|---|---|
| Phone API (HTTPS + mTLS) | `10.90.91.1` | **8743** |
| Admin (HTTP) | `127.0.0.1` | **8744** |

Not 6379, 8188, 11434, 11435, or 8765. Phone bind is never `0.0.0.0` and
never `10.90.90.x`.

## Run

From the repository root, system Python (not the farm venv):

```
python -m unittest local_agent.edge_gateway.test_edge_gateway -v
python -m local_agent.edge_gateway --data-dir local_agent/edge_gateway/runtime --listen
```

`--listen` fails if `10.90.91.1` is not on an interface. Create the isolated
overlay with `Generate-EdgePhoneOverlay.ps1` (does not edit the farm hub).
Do not pass `-Install` until the operator is ready to bring the `/30` up.

## Admin (loopback)

- `POST /v1/admin/devices` `{"device_id":"pixel1"}` — token + client cert once. USB/ADB only (G5).
- `POST /v1/admin/jobs` `{"prompt":"...","max_tokens":32}` — operator injects the one prompt (G6).
- `POST /v1/admin/devices/pixel1/revoke` — expires the lease; complete is then 401 (G8).
- `GET /v1/admin/jobs/{id}` — includes `untrusted: true` and the stored blob (G7).

## Phone contract

Same paths as `termux_powerinfer2_edge_worker.py`:
`POST /v1/edge/jobs/claim`, `POST /v1/edge/jobs/{id}/complete`.
Bearer token + mTLS (G2). Caps re-enforced on the server.
