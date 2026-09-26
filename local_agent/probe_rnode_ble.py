#!/usr/bin/env python3
"""Read-only RNode BLE detection helper.

Connects to a paired RNode Nordic-UART BLE service and sends only the RNode
KISS detect, firmware-version, platform, and MCU queries. It never changes
frequency, bandwidth, spreading factor, coding rate, transmit power, radio
state, or firmware.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from bleak import BleakClient, BleakScanner
from winrt.windows.devices.bluetooth import BluetoothLEDevice

UART_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
UART_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"
UART_TX_CHAR_UUID = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E"

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


async def probe(address: str) -> dict[str, object]:
    started = time.monotonic()
    bluetooth_address = int(address.replace(":", ""), 16)
    paired_device = await BluetoothLEDevice.from_bluetooth_address_async(bluetooth_address)
    windows_paired = paired_device is not None
    def is_target(device: object, advertisement: object) -> bool:
        device_address = str(getattr(device, "address", "")).lower()
        services = [str(item).lower() for item in getattr(advertisement, "service_uuids", [])]
        return device_address == address.lower() and UART_SERVICE_UUID.lower() in services

    # This is deliberately the same connectable-device discovery method used
    # by Reticulum's BLE RNode interface, rather than a raw advertising list.
    device = await BleakScanner.find_device_by_filter(is_target, timeout=4)
    if device is None:
        return {
            "address": address,
            "windows_paired": windows_paired,
            "advertising": False,
            "rnode_detected": False,
        }
    device_details = str(getattr(device, "details", ""))
    if not windows_paired:
        return {
            "address": address,
            "name": device.name,
            "advertising": True,
            "windows_paired": False,
            "device_details": device_details,
            "rnode_detected": False,
            "error": "Windows can see this RNode, but it is not paired for BLE GATT access.",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    received = bytearray()

    def on_receive(_: object, data: bytearray) -> None:
        received.extend(data)

    try:
        async with BleakClient(device) as client:
            services = client.services
            service = services.get_service(UART_SERVICE_UUID)
            if service is None:
                return {
                    "address": address,
                    "name": device.name,
                    "advertising": True,
                    "windows_paired": True,
                    "device_details": device_details,
                    "uart_service": False,
                    "rnode_detected": False,
                }
            await client.start_notify(UART_TX_CHAR_UUID, on_receive)
            await client.write_gatt_char(UART_RX_CHAR_UUID, PROBE, response=False)
            await asyncio.sleep(2)
    except Exception as exc:
        return {
            "address": address,
            "name": device.name,
            "advertising": True,
            "windows_paired": True,
            "device_details": device_details,
            "rnode_detected": False,
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.monotonic() - started, 2),
        }

    raw = bytes(received)
    return {
        "address": address,
        "name": device.name,
        "advertising": True,
        "windows_paired": True,
        "device_details": device_details,
        "uart_service": True,
        "rnode_detected": DETECT_REPLY in raw,
        "response_hex": raw.hex(),
        "elapsed_seconds": round(time.monotonic() - started, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", default="3C:0F:02:EC:0A:65", help="Paired PC-side RNode BLE address")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(probe(args.address)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
