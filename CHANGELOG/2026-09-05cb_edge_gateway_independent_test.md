# 2026-09-05cb — Edge gateway independent workstation test (G6–G9)

Date: 2026-09-05. Host: DuranGamingPC. Id from
`python scripts/next_changelog_id.py`: **2026-09-05cb**.

Live gateway PID 46176, phone URL `https://10.90.91.1:8743` (overlay, not
loopback), admin `http://127.0.0.1:8744`. Client:
`local_agent/edge_gateway/independent_live_test.py`. Device `ws-indep-1`
(not `pixel1`). Prompt `2+2` only. No Termux, no farm `.env` edit, no
ComfyUI, no Equal Shares.

## Results — all passed

| Check | Evidence |
|---|---|
| Happy path | inject `N_5Iq0bkyCNUJ6vParWhoA` → claim → complete `synthetic-ok`; admin GET `untrusted: true`, result unchanged |
| Second claim during lease | **idempotent same job id** (not 409) |
| Mutated complete | HTTP **409** `replay conflict`; stored result still `synthetic-ok` |
| Oversized inject | HTTP **400** `prompt exceeds the edge limit` |
| Revoked claim | HTTP **401** body `{"error":"unauthorized"}` — no `job`, no prompt |
| No second queued job | sqlite: 1 row, state `completed`, queued_count 0 |
| Sockets | `10.90.91.1:8743` connect_ex=0; `127.0.0.1:8744`=0; `0.0.0.0:8743`=10049 |
| Env | CommandLine is `-m local_agent.edge_gateway --data-dir local_agent/edge_gateway/runtime --listen`. Forbidden keys **absent**: `REDIS_PASSWORD`, `FARM_BROKER_URL`, AES names. Farm `.env` files exist on disk but were not in argv. Inherited user env does contain `FARM_REDIS_ENGINE` (engine selector, not a secret). |

## Gateway logs from this run (quoted)

```
{"event":"error","http_status":400,"path":"/v1/admin/jobs","peer_ip":"127.0.0.1","reason":"prompt exceeds the edge limit","ts":"2026-09-05T21:01:01.182660+00:00"}
{"event":"job_injected","http_status":201,"job_id":"N_5Iq0bkyCNUJ6vParWhoA","path":"/v1/admin/jobs","prompt_chars":3,"ts":"2026-09-05T21:01:04.787501+00:00"}
{"device_id":"ws-indep-1","event":"claim","http_status":200,"job_id":"N_5Iq0bkyCNUJ6vParWhoA","path":"/v1/edge/jobs/claim","peer_ip":"10.90.91.1","prompt_chars":3,"ts":"2026-09-05T21:01:05.106929+00:00"}
{"device_id":"ws-indep-1","event":"claim","http_status":200,"job_id":"N_5Iq0bkyCNUJ6vParWhoA","path":"/v1/edge/jobs/claim","peer_ip":"10.90.91.1","prompt_chars":3,"ts":"2026-09-05T21:01:05.123971+00:00"}
{"device_id":"ws-indep-1","event":"complete","http_status":200,"job_id":"N_5Iq0bkyCNUJ6vParWhoA","path":"/v1/edge/jobs/N_5Iq0bkyCNUJ6vParWhoA/complete","peer_ip":"10.90.91.1","result_chars":12,"status":"completed","ts":"2026-09-05T21:01:05.138990+00:00"}
```

No prompt text (`2+2`), no result text (`synthetic-ok`), no bearer token,
no farm secret strings in those lines. Sizes only (`prompt_chars`: 3,
`result_chars`: 12).

**G6–G9 accepted, independent test passed.** G10 (Pixel `--once`) is
unblocked pending operator go-ahead. Phone/Termux were not used.
