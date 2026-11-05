#!/usr/bin/env python3
"""Conservative GPU thermal gate shared by the Equal Shares render stages."""
from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


NVIDIA_SMI = Path(os.environ.get(
    "NVIDIA_SMI_PATH", r"C:\Windows\System32\nvidia-smi.exe",
))
START_MAX_C = int(os.environ.get("EQUAL_SHARES_GPU_START_MAX_C", "70"))
START_RESUME_C = int(os.environ.get("EQUAL_SHARES_GPU_START_RESUME_C", "60"))
POST_JOB_C = int(os.environ.get("EQUAL_SHARES_GPU_POST_JOB_C", "58"))
EMERGENCY_C = int(os.environ.get("EQUAL_SHARES_GPU_EMERGENCY_C", "82"))
POLL_SECONDS = int(os.environ.get("EQUAL_SHARES_THERMAL_POLL_SECONDS", "15"))


@dataclass(frozen=True)
class GpuSample:
    temperature_c: int
    utilization_percent: int
    power_watts: float


class ThermalTelemetryError(RuntimeError):
    pass


class ThermalLimitExceeded(RuntimeError):
    pass


def sample_gpu() -> GpuSample:
    if not NVIDIA_SMI.is_file():
        raise ThermalTelemetryError(f"nvidia-smi not found: {NVIDIA_SMI}")
    result = subprocess.run(
        [
            str(NVIDIA_SMI),
            "--query-gpu=temperature.gpu,utilization.gpu,power.draw",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise ThermalTelemetryError(result.stderr.strip() or "nvidia-smi failed")
    first = next((line for line in result.stdout.splitlines() if line.strip()), "")
    parts = [part.strip() for part in first.split(",")]
    if len(parts) != 3:
        raise ThermalTelemetryError(f"unexpected nvidia-smi output: {first!r}")
    try:
        return GpuSample(int(parts[0]), int(parts[1]), float(parts[2]))
    except ValueError as exc:
        raise ThermalTelemetryError(f"unreadable nvidia-smi output: {first!r}") from exc


def _wait_until(
    target_c: int,
    emit: Callable[[str], None],
    reason: str,
) -> GpuSample:
    last_report = 0.0
    telemetry_failures = 0
    while True:
        try:
            sample = sample_gpu()
            telemetry_failures = 0
        except ThermalTelemetryError:
            telemetry_failures += 1
            if telemetry_failures >= 3:
                raise
            time.sleep(POLL_SECONDS)
            continue
        if sample.temperature_c <= target_c:
            return sample
        now = time.time()
        if not last_report or now - last_report >= 60:
            emit(
                f"Thermal cooldown: GPU {sample.temperature_c} C, "
                f"{sample.utilization_percent}% use, {sample.power_watts:.0f} W; "
                f"waiting for <= {target_c} C before {reason}"
            )
            last_report = now
        time.sleep(POLL_SECONDS)


def wait_before_render(emit: Callable[[str], None]) -> GpuSample:
    sample = sample_gpu()
    if sample.temperature_c <= START_MAX_C:
        emit(
            f"Thermal preflight passed: GPU {sample.temperature_c} C, "
            f"{sample.utilization_percent}% use, {sample.power_watts:.0f} W"
        )
        return sample
    emit(
        f"Thermal preflight hold: GPU {sample.temperature_c} C exceeds "
        f"the {START_MAX_C} C start ceiling"
    )
    return _wait_until(START_RESUME_C, emit, "starting the next render")


def wait_after_render(emit: Callable[[str], None]) -> GpuSample:
    return _wait_until(POST_JOB_C, emit, "the next GPU job")


def check_running_ceiling(emit: Callable[[str], None], clip_id: str) -> GpuSample:
    sample = sample_gpu()
    if sample.temperature_c >= EMERGENCY_C:
        emit(
            f"THERMAL STOP {clip_id}: GPU reached {sample.temperature_c} C "
            f"at {sample.power_watts:.0f} W; interrupting this attempt and cooling"
        )
        raise ThermalLimitExceeded(
            f"GPU {sample.temperature_c} C reached {EMERGENCY_C} C emergency ceiling"
        )
    return sample
