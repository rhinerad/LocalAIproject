#!/usr/bin/env python3
"""Drive Sonic Pi from the local agent at http://127.0.0.1:8760.

Two OSC channels, matching Sonic Pi 4/5:

  1. Spider API (GUI port + session token) — actually evals Ruby / hard-stops.
  2. Cue port 4560 /run-code — what sonic-pi-queue.rb listens to for DJ segments.

The agent is not an MCP client. These helpers speak OSC directly.
"""
from __future__ import annotations

import json
import os
import re
import socket
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
QUEUE_RB = HERE / "sonic-pi-queue.rb"
INIT_RB = Path.home() / ".sonic-pi" / "config" / "init.rb"
WORKSPACE_ZERO = Path.home() / ".sonic-pi" / "store" / "default" / "workspace_zero.spi"
SONIC_PI_EXE = Path(os.environ.get(
    "SONIC_PI_EXE",
    r"C:\Program Files\Sonic Pi\app\gui\build\Release\sonic-pi.exe",
))
BEGIN = "# BEGIN local-agent-sonic-pi-queue"
END = "# END local-agent-sonic-pi-queue"
SPIDER_RE = re.compile(
    r"spider-server\.rb.*?-u\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)",
    re.IGNORECASE | re.DOTALL,
)

OSC_HOST = os.environ.get("OSC_HOST", "127.0.0.1")
OSC_PORT = int(os.environ.get("OSC_PORT", "4560"))
OSC_CODE_PATH = os.environ.get("OSC_CODE_PATH", "/run-code")
OSC_STOP_ALL_PATH = os.environ.get("OSC_STOP_ALL_PATH", "/stop-all-jobs")

_queue_injected = False


def _pad4(data: bytes) -> bytes:
    pad = (4 - (len(data) % 4)) % 4
    return data + (b"\x00" * pad)


def osc_string(value: str) -> bytes:
    return _pad4(value.encode("utf-8") + b"\x00")


def encode_osc(path: str, *args: Any) -> bytes:
    """Build a single OSC message (address + type tags + arguments)."""
    parts = [osc_string(path)]
    tags = [","]
    payloads: list[bytes] = []
    for arg in args:
        if isinstance(arg, str):
            tags.append("s")
            payloads.append(osc_string(arg))
        elif isinstance(arg, bool):
            tags.append("T" if arg else "F")
        elif isinstance(arg, int):
            tags.append("i")
            payloads.append(struct.pack(">i", int(arg)))
        elif isinstance(arg, float):
            tags.append("f")
            payloads.append(struct.pack(">f", arg))
        else:
            raise TypeError(f"unsupported OSC type: {type(arg).__name__}")
    parts.append(osc_string("".join(tags)))
    parts.extend(payloads)
    return b"".join(parts)


def send_osc(path: str, *args: Any, host: str | None = None, port: int | None = None) -> dict:
    dest_host = host or OSC_HOST
    dest_port = OSC_PORT if port is None else port
    packet = encode_osc(path, *args)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(1.0)
        sent = sock.sendto(packet, (dest_host, dest_port))
    except OSError as exc:
        raise RuntimeError(
            f"OSC send to {dest_host}:{dest_port} {path} failed: {exc}. "
            "Is Sonic Pi open with incoming OSC enabled?"
        ) from exc
    finally:
        sock.close()
    return {
        "ok": True,
        "host": dest_host,
        "port": dest_port,
        "path": path,
        "bytes": sent,
    }


def queue_runner_source() -> str:
    if not QUEUE_RB.is_file():
        raise RuntimeError(f"missing queue runner at {QUEUE_RB}")
    return QUEUE_RB.read_text(encoding="utf-8")


def install_queue_runner() -> dict:
    """Persist the DJ runner in Sonic Pi init.rb so it starts on every launch."""
    source = queue_runner_source()
    block = f"{BEGIN}\n{source.rstrip()}\n{END}\n"
    INIT_RB.parent.mkdir(parents=True, exist_ok=True)
    existing = INIT_RB.read_text(encoding="utf-8") if INIT_RB.is_file() else (
        "# Sonic Pi init file\n# Code in here will be evaluated on launch.\n"
    )
    if BEGIN in existing and END in existing:
        start = existing.index(BEGIN)
        stop = existing.index(END) + len(END)
        updated = existing[:start] + block.strip() + existing[stop:]
    else:
        updated = existing.rstrip() + "\n\n" + block
    INIT_RB.write_text(updated, encoding="utf-8")
    if WORKSPACE_ZERO.parent.is_dir():
        WORKSPACE_ZERO.write_text(source, encoding="utf-8")
    return {"ok": True, "init_rb": str(INIT_RB), "workspace": str(WORKSPACE_ZERO)}


def discover_spider(command_line: str | None = None) -> dict | None:
    text = command_line if command_line is not None else _spider_command_line()
    if not text:
        return None
    match = SPIDER_RE.search(text)
    if not match:
        return None
    return {
        "server_port": int(match.group(1)),
        "gui_port": int(match.group(2)),
        "osc_cues_port": int(match.group(5)),
        "token": int(match.group(6)),
    }


def _spider_command_line() -> str:
    ps = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.CommandLine -like '*spider-server.rb*' } | "
        "Select-Object -ExpandProperty CommandLine"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout or ""


def inject_queue_runner(spider: dict | None = None) -> dict:
    spider = spider or discover_spider()
    if not spider:
        raise RuntimeError("Sonic Pi spider API is not running")
    source = queue_runner_source()
    result = send_osc(
        "/run-code", spider["token"], source,
        host="127.0.0.1", port=spider["server_port"],
    )
    result["injected"] = True
    result["via"] = "spider"
    return result


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    """Best-effort UDP reachability. OSC cues are UDP, so TCP connect is the wrong check."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.sendto(encode_osc("/ping"), (host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def start_sonic_pi() -> dict:
    if not SONIC_PI_EXE.is_file():
        raise RuntimeError(f"Sonic Pi executable not found: {SONIC_PI_EXE}")
    subprocess.Popen(
        [str(SONIC_PI_EXE)],
        cwd=str(SONIC_PI_EXE.parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return {"started": True, "exe": str(SONIC_PI_EXE)}


def ensure_sonic_pi(args: dict | None = None) -> str:
    """Install the queue runner, start Sonic Pi if needed, inject the listener."""
    global _queue_injected
    args = args or {}
    timeout = float(args.get("timeout") or 90)
    report: dict[str, Any] = {"install": install_queue_runner()}
    spider = discover_spider()
    if spider is None:
        report["launch"] = start_sonic_pi()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            spider = discover_spider()
            if spider:
                break
            time.sleep(1.0)
    if spider is None:
        raise RuntimeError(
            f"Sonic Pi did not expose its spider API within {timeout:.0f}s. "
            "Open Sonic Pi once and wait until the GUI has finished booting."
        )
    report["spider"] = {
        "server_port": spider["server_port"],
        "osc_cues_port": spider["osc_cues_port"],
    }
    # OSC cues are UDP. If we just launched Sonic Pi, wait briefly for SuperCollider.
    # If spider was already running, do not burn 30s on a reachability loop.
    launched = "launch" in report
    if launched:
        cues_deadline = time.monotonic() + 15
        while time.monotonic() < cues_deadline and not port_open(
                OSC_HOST, spider["osc_cues_port"]):
            time.sleep(0.5)
    report["osc_cues_open"] = port_open(OSC_HOST, spider["osc_cues_port"])
    report["inject"] = inject_queue_runner(spider)
    _queue_injected = True
    report["ok"] = True
    return json.dumps(report)


def _maybe_inject_queue() -> None:
    global _queue_injected
    if _queue_injected:
        return
    spider = discover_spider()
    if not spider:
        return
    try:
        inject_queue_runner(spider)
        _queue_injected = True
    except Exception:
        return


def queue_segment(args: dict) -> str:
    code = str(args.get("code", "")).strip()
    if not code:
        raise RuntimeError("code is required — send a full Sonic Pi Ruby segment")
    _maybe_inject_queue()
    result = send_osc(OSC_CODE_PATH, code)
    result["queued"] = True
    result["chars"] = len(code)
    return json.dumps(result)


def play_note(args: dict) -> str:
    try:
        note = int(args.get("note", 60))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("note must be a MIDI number 0-127") from exc
    if note < 0 or note > 127:
        raise RuntimeError("note must be a MIDI number 0-127")
    synth = str(args.get("synth") or ":beep").strip() or ":beep"
    if not synth.startswith(":"):
        synth = ":" + synth
    sustain = float(args.get("sustain") or 1)
    cutoff = float(args.get("cutoff") or 100)
    snippet = (
        f"use_synth {synth}\n"
        f"play {note}, sustain: {sustain}, cutoff: {cutoff}\n"
    )
    spider = discover_spider()
    if spider:
        result = send_osc(
            "/run-code", spider["token"], snippet,
            host="127.0.0.1", port=spider["server_port"],
        )
        result["via"] = "spider"
    else:
        _maybe_inject_queue()
        result = send_osc(OSC_CODE_PATH, snippet)
        result["via"] = "osc-cues"
    result.update({"note": note, "synth": synth, "sustain": sustain, "cutoff": cutoff})
    return json.dumps(result)


def stop_all(_: dict) -> str:
    spider = discover_spider()
    if spider:
        result = send_osc(
            "/stop-all-jobs", spider["token"],
            host="127.0.0.1", port=spider["server_port"],
        )
        result["via"] = "spider"
    else:
        result = send_osc(OSC_STOP_ALL_PATH)
        result["via"] = "osc-cues"
    result["stopped"] = True
    return json.dumps(result)
