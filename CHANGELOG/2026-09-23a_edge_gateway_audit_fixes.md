# 2026-09-23a — edge gateway audit fixes, stopped before phone cutover

Code and host ACL changes from the 2026-09-23 edge audit were applied. Firewall
narrowing, proxy shutdown, phone private-launcher install, and credential
rotation were not. The operator said stop after the gateway had already been
restarted onto this code.

## Code

- Ledger: expire every overdue lease inside claim, admin view, and complete.
  A live lease is not handed to a second claim. Completion requires the owning
  device, the attempt number, and an unexpired lease. Replay of a stored result
  is limited to that owner. Queue cap 32. Terminal rows older than 14 days are
  deleted on inject. Context check rejects prompts that cannot share the
  512-token phone window with generation. Body cap is 262144 bytes.
- TLS material: device ids are checked before any certificate file is written.
  `../escaped` no longer creates a sibling directory. An existing device
  directory is not overwritten.
- Admin API requires a bearer token from `runtime/admin.token`. The file was
  created on the restarted gateway. Its contents were not printed.
- Phone TLS handshake runs on the worker thread with a 10s handshake timeout,
  a 30s request timeout, and a cap of 4 in-flight connections.
- Worker: gateway host pinned to `https://10.90.91.1` unless loopback is
  explicitly allowed with `EDGE_TLS_PIN_SHA256`. Redirects are refused.
  `EDGE_SSL_NO_HOSTNAME` no longer disables name checks. Completion is retried
  from a private outbox. Stdout and stderr captures are capped. Every runtime
  branch passes `-c 512` and `-ub 4`.
- Desktop proxy and client response bodies are capped and the proxy closes the
  backend response on success and error paths.
- Private phone launcher sources are `local_agent/worker_farm/phone/edge_boot.py`
  and `edge_watch.py`. The same bytes were copied to `practice-score\work`.
  They were not installed on the phone.

## Verification

`python -m unittest local_agent.edge_gateway.test_edge_gateway local_agent.worker_farm.test_termux_powerinfer2_edge_worker` — 27 tests, OK. No model inference.

## Host

Runtime DACLs under `local_agent/edge_gateway/runtime` were rebuilt so files
allow only `NT AUTHORITY\SYSTEM`, `BUILTIN\Administrators`, and
`DURANGAMINGPC\rhine`. The first `icacls /grant` used directory-only
`(OI)(CI)` flags on files and left those files with an empty DACL. Explicit
file grants were applied before the gateway was started again. Confirmed on
`tls\ca.key.pem`, `edge_ledger.sqlite3`, and `admin.token`.

The previous gateway PID 22000 was stopped. The replacement is listening on
`10.90.91.1:8743` and `127.0.0.1:8744` (PID 40300 at restart). The phone still
runs the previous worker, which does not send `attempt`, so a live completion
from that worker is rejected until the phone copy is updated.
