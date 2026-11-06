#!/usr/bin/env python3
"""Read-only RNode Bluetooth/serial detection helper.

This sends only the RNode KISS detect/version/platform/MCU query. It never
sets frequency, bandwidth, spreading factor, coding rate, power, or radio state.
Use it to identify which Windows Bluetooth serial endpoint is the paired RNode
before adding an RNodeInterface to Reticulum.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "vendor"))

import serial
import serial.tools.list_ports

FEND = 0xC0
CMD_DETECT = 0x08
DETECT_REQ = 0x73
CMD_FW_VERSION = 0x50
CMD_PLATFORM = 0x48
CMD_MCU = 0x49
DETECT_REPLY = bytes([FEND, CMD_DETECT, 0x46, FEND])
PROBE = bytes([
    FEND, CMD_DETECT, DETECT_REQ, FEND,
    CMD_FW_VERSION, 0x00, FEND,
    CMD_PLATFORM, 0x00, FEND,
    CMD_MCU, 0x00, FEND,
])


def candidates() -> list[str]:
    return [p.device for p in serial.tools.list_ports.comports()
            if "bluetooth" in (p.description or "").lower()]


def probe(port: str) -> dict:
    started = time.monotonic()
    try:
        with serial.Serial(port, 115200, timeout=0.25, write_timeout=1,
                           rtscts=False, dsrdtr=False) as device:
            # Avoid asserting control lines; RNode traffic is KISS over data only.
            device.dtr = False
            device.rts = False
            # Some ESP32 USB bridges reset the MCU as the port opens. Let the
            # RNode firmware finish booting before the read-only KISS query.
            time.sleep(1.5)
            device.reset_input_buffer()
            device.write(PROBE)
            device.flush()
            deadline = time.monotonic() + 2.0
            data = b""
            while time.monotonic() < deadline:
                data += device.read(256)
                if DETECT_REPLY in data:
                    break
        return {
            "port": port,
            "opened": True,
            "rnode_detected": DETECT_REPLY in data,
            "response_hex": data.hex(),
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }
    except Exception as exc:
        return {
            "port": port,
            "opened": False,
            "rnode_detected": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ports", nargs="*", help="COM ports to probe; defaults to Bluetooth ports")
    args = parser.parse_args()
    ports = args.ports or candidates()
    if not ports:
        print("No Bluetooth serial ports found.")
        return 1
    for port in ports:
        print(probe(port))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
