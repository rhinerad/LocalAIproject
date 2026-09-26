# 2026-09-03ay — tunnel-relay treats WinError 121 as expected peer disconnect

Cosmetic follow-up to `2026-09-03av`. `_pump` already swallowed
`ConnectionResetError` / `BrokenPipeError` as "client went away" and let
`OSError: [WinError 121] The semaphore timeout period has expired`
(ERROR_SEM_TIMEOUT) bubble out of `asyncio.gather`, which asyncio logged as
`Unhandled exception in client_connected_cb`. Same benign condition — Mac
reboot or sleep-without-keepalive — different OS error code.

Id from `python scripts/next_changelog_id.py` immediately before write:
**2026-09-03ay**.

## Change

`local_agent/worker_farm/relay/tunnel_relay.py`:

- `_is_expected_disconnect(exc)` is true for `ConnectionResetError`,
  `BrokenPipeError`, and `OSError` whose **`winerror` is 121**. POSIX
  `errno` 121 is not treated as this case (`OSError(121, ...)` has
  `winerror is None`).
- `_pump` catches `OSError`, re-raises if not expected, otherwise
  `log.info("peer disconnected (%s)", exc)` instead of a traceback.
- Other Winsock `OSError`s (e.g. WinError 10048) still propagate.

No task XML change. Live `\local-agent-tunnel-relay` process still runs the
old code until the next logon/task restart; this is source + tests only.

## Tests

```
local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_tunnel_relay -v
```

6 tests, all OK. `test_pump_logs_winerror_121_as_peer_disconnected_not_error`
raises a constructed `[WinError 121]` from a fake reader, asserts an INFO
`peer disconnected` line containing `121`, and asserts no ERROR records.
`test_pump_reraises_unrelated_oserror` uses WinError 10048 and expects the
exception. `test_errno_121_without_winerror_is_not_expected` keeps the
scope off POSIX errno 121.
