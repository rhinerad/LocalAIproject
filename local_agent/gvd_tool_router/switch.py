"""Model-family switch protocol. /free is a request, not proof of empty VRAM."""
from __future__ import annotations

from typing import Any, Callable, Protocol

from .gpu_lease import LeaseContention, acquire
from .paths import GvdLayout

HEADROOM_MIB = 2048
APPROVAL_HEADROOM_MIB = 512


class QueueProbe(Protocol):
    def pending_and_running(self) -> tuple[int, int]: ...
    def foreign_jobs(self) -> bool: ...


class MemoryProbe(Protocol):
    def free_mib(self) -> int | None: ...
    def used_mib(self) -> int | None: ...


class SwitchBlocked(RuntimeError):
    pass


def switch_to(
    layout: GvdLayout,
    target_family: str,
    *,
    peak_gpu_mib: int | None,
    job_id: str,
    attempt_id: str,
    queue: QueueProbe,
    memory: MemoryProbe,
    unload_ollama: Callable[[], None],
    comfy_free: Callable[[], Any],
    restart_owned_idle_worker: Callable[[], None] | None = None,
    operator_approval: bool = False,
) -> dict[str, Any]:
    if peak_gpu_mib is None:
        raise SwitchBlocked("PROFILE_REQUIRED")
    with acquire(layout, job_id=job_id, attempt_id=attempt_id, family_key=target_family) as lease:
        pending, running = queue.pending_and_running()
        if pending or running:
            return {
                "status": "waiting_queue",
                "pending": pending,
                "running": running,
                "lease_generation": lease.generation,
            }
        if queue.foreign_jobs():
            raise SwitchBlocked("RESOURCE_BLOCKED:foreign_jobs")
        unload_ollama()
        comfy_free()
        free = memory.free_mib()
        used = memory.used_mib()
        if free is None or used is None:
            raise SwitchBlocked("telemetry_unavailable")
        # Explicit operator approval may lower the headroom floor for flagged
        # tight profiles (e.g. FastH3 V2). It never removes the floor entirely.
        headroom = APPROVAL_HEADROOM_MIB if operator_approval else HEADROOM_MIB
        if peak_gpu_mib + headroom > free:
            if restart_owned_idle_worker is not None:
                restart_owned_idle_worker()
                free = memory.free_mib()
                if free is None or peak_gpu_mib + headroom > free:
                    raise SwitchBlocked("RESOURCE_BLOCKED")
            else:
                raise SwitchBlocked("RESOURCE_BLOCKED")
        return {
            "status": "admitted",
            "family": target_family,
            "lease_generation": lease.generation,
            "free_mib": free,
            "used_mib": used,
            "headroom_mib": headroom,
            "operator_approval": operator_approval,
        }
