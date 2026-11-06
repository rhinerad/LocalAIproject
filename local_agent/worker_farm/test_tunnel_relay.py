r"""Tunnel-relay expected-disconnect tests.

Correct invocation — from the repository root, farm venv only:

  local_agent\worker_farm\.venv\Scripts\python.exe -m unittest local_agent.worker_farm.test_tunnel_relay -v

Do not run this file by path. PATH Python is not the farm environment.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import unittest

_FARM_UNITTEST = (
    r"local_agent\worker_farm\.venv\Scripts\python.exe -m unittest "
    "local_agent.worker_farm.test_tunnel_relay -v"
)


def _require_package_layout() -> None:
    try:
        import local_agent.worker_farm  # noqa: F401
    except ModuleNotFoundError as exc:
        if getattr(exc, "name", None) not in {"local_agent", "local_agent.worker_farm"}:
            raise
        sys.stderr.write(
            "ERROR: local_agent is not importable because this file was run by path.\n"
            "From the repository root, use the farm venv:\n"
            f"  {_FARM_UNITTEST}\n"
        )
        raise SystemExit(2) from exc


_require_package_layout()

from local_agent.worker_farm.relay import tunnel_relay


def _winerror(code: int, message: str) -> OSError:
    """Build the Windows-form OSError (`[WinError N] ...`, .winerror set)."""
    return OSError(None, message, None, code)


class _RaisingReader:
    def __init__(self, exc: BaseException) -> None:
        self._exc = exc

    async def read(self, n: int) -> bytes:
        raise self._exc


class _SinkWriter:
    def __init__(self) -> None:
        self.closed = False
        self.written: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


class TunnelRelayDisconnectTests(unittest.TestCase):
    def test_winerror_121_is_expected_disconnect(self):
        exc = _winerror(121, "The semaphore timeout period has expired")
        self.assertEqual(exc.winerror, 121)
        self.assertTrue(tunnel_relay._is_expected_disconnect(exc))

    def test_errno_121_without_winerror_is_not_expected(self):
        """POSIX errno 121 is not ERROR_SEM_TIMEOUT; do not swallow it."""
        exc = OSError(121, "The semaphore timeout period has expired")
        self.assertIsNone(getattr(exc, "winerror", None))
        self.assertFalse(tunnel_relay._is_expected_disconnect(exc))

    def test_other_winerror_is_not_expected(self):
        exc = _winerror(10048, "Address already in use")
        self.assertFalse(tunnel_relay._is_expected_disconnect(exc))

    def test_connection_reset_and_broken_pipe_stay_expected(self):
        self.assertTrue(tunnel_relay._is_expected_disconnect(ConnectionResetError()))
        self.assertTrue(tunnel_relay._is_expected_disconnect(BrokenPipeError()))

    def test_pump_logs_winerror_121_as_peer_disconnected_not_error(self):
        exc = _winerror(121, "The semaphore timeout period has expired")
        reader = _RaisingReader(exc)
        writer = _SinkWriter()
        with self.assertLogs(tunnel_relay.log, level="INFO") as captured:
            asyncio.run(tunnel_relay._pump(reader, writer))
        self.assertTrue(writer.closed)
        info_lines = [r.getMessage() for r in captured.records if r.levelno == logging.INFO]
        error_lines = [r.getMessage() for r in captured.records if r.levelno >= logging.ERROR]
        self.assertTrue(
            any("peer disconnected" in line and "121" in line for line in info_lines),
            info_lines,
        )
        self.assertEqual(error_lines, [])

    def test_pump_reraises_unrelated_oserror(self):
        exc = _winerror(10048, "Address already in use")
        reader = _RaisingReader(exc)
        writer = _SinkWriter()
        with self.assertRaises(OSError) as ctx:
            asyncio.run(tunnel_relay._pump(reader, writer))
        self.assertEqual(ctx.exception.winerror, 10048)
        self.assertTrue(writer.closed)


if __name__ == "__main__":
    unittest.main()
