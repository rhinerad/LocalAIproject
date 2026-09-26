"""Stdlib-only TCP relay: WireGuard tunnel interface -> loopback Redis.

This is plumbing, not a security boundary. It adds no authentication of its
own and forwards raw bytes unmodified. The two real security layers are the
WireGuard tunnel underneath it (encryption + peer authentication) and the
Redis ACL credential inside the relayed connection (see
Add-Phase1SecondaryWorkerCredential.ps1). This relay exists only because
compose.yaml's already-verified `127.0.0.1:6379:6379` publish rule is
deliberately left untouched rather than risking an unverified change to a
working foundation; see docs/WORKER_FARM_PHASE1_5_SECONDARY_NODE_PLAN_2026-08-29.md.

Refuses to bind to 0.0.0.0 or any loopback address -- it must be told an
explicit, real tunnel-interface IP. It is not started by any existing
launcher and does not run automatically.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s relay %(message)s")
log = logging.getLogger("tunnel_relay")

MAX_CONCURRENT_CONNECTIONS = 64
CHUNK_BYTES = 65536
# Windows ERROR_SEM_TIMEOUT: overlapped recv timed out because the peer
# vanished without RST/FIN (Mac reboot / sleep with TCPKeepAlive off).
# Must match OSError.winerror, not errno -- POSIX errno 121 is unrelated.
WINERR_SEM_TIMEOUT = 121


class RelayPolicyError(ValueError):
    """Raised before the relay will bind to a caller-supplied address."""


def _validate_bind_ip(value: str) -> str:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError as exc:
        raise RelayPolicyError(f"{value!r} is not a valid IP address") from exc
    if parsed.is_unspecified:
        raise RelayPolicyError("refusing to bind 0.0.0.0 / ::  -- name the tunnel interface IP explicitly")
    if parsed.is_loopback:
        raise RelayPolicyError("refusing to bind a loopback address -- that traffic already reaches Redis directly")
    if parsed.is_multicast:
        raise RelayPolicyError("refusing to bind a multicast address")
    return str(parsed)


def _is_expected_disconnect(exc: BaseException) -> bool:
    """True for a client that went away, not a bind/listen/upstream failure."""
    if isinstance(exc, (ConnectionResetError, BrokenPipeError)):
        return True
    if isinstance(exc, OSError) and getattr(exc, "winerror", None) == WINERR_SEM_TIMEOUT:
        return True
    return False


async def _pump(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while True:
            chunk = await reader.read(CHUNK_BYTES)
            if not chunk:
                break
            writer.write(chunk)
            await writer.drain()
    except OSError as exc:
        if not _is_expected_disconnect(exc):
            raise
        log.info("peer disconnected (%s)", exc)
    finally:
        writer.close()


def make_handler(target_host: str, target_port: int, semaphore: asyncio.Semaphore):
    async def handle(client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter) -> None:
        peer = client_writer.get_extra_info("peername")
        async with semaphore:
            log.info("connection from %s", peer)
            try:
                upstream_reader, upstream_writer = await asyncio.open_connection(target_host, target_port)
            except OSError as exc:
                log.warning("could not reach upstream %s:%s (%s); dropping %s", target_host, target_port, exc, peer)
                client_writer.close()
                return
            try:
                await asyncio.gather(
                    _pump(client_reader, upstream_writer),
                    _pump(upstream_reader, client_writer),
                )
            finally:
                for w in (client_writer, upstream_writer):
                    try:
                        w.close()
                    except OSError:
                        pass
            log.info("connection closed %s", peer)
    return handle


async def run(bind_ip: str, bind_port: int, target_host: str, target_port: int) -> None:
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_CONNECTIONS)
    server = await asyncio.start_server(
        make_handler(target_host, target_port, semaphore), host=bind_ip, port=bind_port,
    )
    log.info("relaying %s:%s -> %s:%s (max %d concurrent)", bind_ip, bind_port, target_host, target_port, MAX_CONCURRENT_CONNECTIONS)
    async with server:
        await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind-ip", required=True, help="the WireGuard tunnel interface IP, e.g. 10.90.90.1 -- never 0.0.0.0")
    parser.add_argument("--bind-port", type=int, default=6379)
    parser.add_argument("--target-host", default="127.0.0.1", help="where the already-running Redis actually listens")
    parser.add_argument("--target-port", type=int, default=6379)
    args = parser.parse_args()
    try:
        bind_ip = _validate_bind_ip(args.bind_ip)
    except RelayPolicyError as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    try:
        asyncio.run(run(bind_ip, args.bind_port, args.target_host, args.target_port))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
