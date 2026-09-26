"""M0 bootstrap inventory. Never starts ComfyUI, never downloads, never installs."""
from __future__ import annotations

import json
import os
import platform
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .paths import GvdLayout, HANDOFF_ROOT, HEADROOM_MIB
from .schema import canonical_json, sha256_json

DEFAULT_COMFY_ROOT = Path(r"A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI")
DEFAULT_COMFY_URL = "http://127.0.0.1:8188"
DEFAULT_OLLAMA_GPU = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_CPU = "http://127.0.0.1:11435"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_commit(path: Path) -> str:
    if not (path / ".git").exists() and not path.exists():
        return "unknown"
    try:
        raw = subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True, timeout=8, stderr=subprocess.DEVNULL,
        )
        return raw.strip() or "unknown"
    except Exception:
        return "unknown"


def _nvidia_query() -> dict[str, Any]:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,compute_cap,driver_version,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True, timeout=8,
        )
        line = raw.strip().splitlines()[0]
        name, cap, driver, total, used, free = [p.strip() for p in line.split(",")]
        return {
            "gpu_name": name,
            "compute_capability": cap,
            "driver_version": driver,
            "memory_total_mib": int(float(total)),
            "memory_used_mib": int(float(used)),
            "memory_free_mib": int(float(free)),
            "telemetry": "nvidia-smi",
        }
    except Exception as exc:
        return {
            "gpu_name": "unknown",
            "compute_capability": "unknown",
            "driver_version": "unknown",
            "memory_total_mib": None,
            "memory_used_mib": None,
            "memory_free_mib": None,
            "telemetry": "unavailable",
            "telemetry_error": type(exc).__name__,
        }


def _http_json(url: str, timeout: float = 3.0) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _port_open(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.4)
    try:
        return sock.connect_ex((host, port)) == 0
    finally:
        sock.close()


def _disk_mib(path: Path) -> int | None:
    try:
        usage = os.statvfs(path)  # type: ignore[attr-defined]
        return int(usage.f_bavail * usage.f_frsize / (1024 * 1024))
    except Exception:
        try:
            import shutil
            return int(shutil.disk_usage(path).free / (1024 * 1024))
        except Exception:
            return None


def _host_ram_mib() -> dict[str, Any]:
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            return {
                "total_mib": int(stat.ullTotalPhys / (1024 * 1024)),
                "available_mib": int(stat.ullAvailPhys / (1024 * 1024)),
            }
    except Exception:
        pass
    return {"total_mib": None, "available_mib": None}


def collect_inventory(*, layout: GvdLayout, comfy_url: str = DEFAULT_COMFY_URL) -> dict[str, Any]:
    """Record installed environment. Does not start or stop services."""
    comfy_root = Path(os.environ.get("GVD_COMFY_ROOT") or DEFAULT_COMFY_ROOT)
    gpu = _nvidia_query()
    object_info = _http_json(f"{comfy_url.rstrip('/')}/object_info", timeout=4.0)
    system_stats = _http_json(f"{comfy_url.rstrip('/')}/system_stats", timeout=3.0)
    schema_sha = sha256_json(object_info) if object_info is not None else (
        "0" * 64
    )
    env_lock = {
        "os": platform.platform(),
        "python_version": sys.version.split()[0],
        "comfy_root": str(comfy_root),
        "comfy_commit": _git_commit(comfy_root),
        "comfy_main_exists": (comfy_root / "main.py").is_file(),
        "comfy_python_exists": (comfy_root / ".venv" / "Scripts" / "python.exe").is_file(),
        "torch_version": "unmeasured",
        "cuda_runtime": "unmeasured",
        "attention_backend": "installed_pytorch_default",
        "gpu": gpu,
        "host_ram": _host_ram_mib(),
        "disk_free_mib": _disk_mib(layout.root if layout.root.exists() else HANDOFF_ROOT),
        "endpoints": {
            "comfyui": comfy_url,
            "ollama_gpu": DEFAULT_OLLAMA_GPU,
            "ollama_cpu": DEFAULT_OLLAMA_CPU,
        },
        "listeners": {
            "8188": _port_open("127.0.0.1", 8188),
            "11434": _port_open("127.0.0.1", 11434),
            "11436": _port_open("127.0.0.1", 11436),
        },
        "object_info_available": object_info is not None,
        "system_stats_available": system_stats is not None,
        "node_schema_sha256": schema_sha if object_info is not None else None,
        "note": "ComfyUI version is user-reported until backend commit is confirmed locally.",
        "collected_at": _utc(),
    }
    if object_info is None:
        env_lock["node_schema_reason"] = "comfy_object_info_unavailable"
    env_lock["environment_sha256"] = sha256_json({
        k: env_lock[k] for k in (
            "os", "python_version", "comfy_commit", "gpu", "endpoints",
        )
    })
    return {
        "schema_version": 1,
        "environment": env_lock,
        "object_info_node_count": len(object_info) if isinstance(object_info, dict) else 0,
        "headroom_mib": HEADROOM_MIB,
    }


def write_runtime_json(layout: GvdLayout, inventory: dict[str, Any]) -> Path:
    layout.ensure()
    env = inventory["environment"]
    payload = {
        "schema_version": 1,
        "comfyui": {
            "base_url": env["endpoints"]["comfyui"],
            "root": env["comfy_root"],
            "commit": env["comfy_commit"],
        },
        "ollama": {
            "gpu_url": env["endpoints"]["ollama_gpu"],
            "cpu_url": env["endpoints"]["ollama_cpu"],
            "keep_alive": 0,
        },
        "gpu": {
            "name": env["gpu"].get("gpu_name"),
            "device_index": 0,
            "headroom_mib": HEADROOM_MIB,
            "compute_capability": env["gpu"].get("compute_capability"),
            "driver_version": env["gpu"].get("driver_version"),
        },
        "policy": {"local_only": True, "discovery_during_render": False},
        "approved_environment_paths": [env["comfy_root"]],
        "written_at": _utc(),
    }
    layout.runtime_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return layout.runtime_json


def persist_inventory(layout: GvdLayout, inventory: dict[str, Any]) -> dict[str, Path]:
    layout.ensure()
    env_path = layout.inventory_dir / "environment_lock.json"
    env_path.write_text(json.dumps(inventory["environment"], indent=2), encoding="utf-8")
    schema_path = layout.inventory_dir / "node_schema_snapshot.json"
    schema_meta = {
        "available": inventory["environment"].get("object_info_available"),
        "node_count": inventory.get("object_info_node_count"),
        "sha256": inventory["environment"].get("node_schema_sha256"),
        "reason": inventory["environment"].get("node_schema_reason"),
        "collected_at": inventory["environment"].get("collected_at"),
    }
    schema_path.write_text(json.dumps(schema_meta, indent=2), encoding="utf-8")
    runtime = write_runtime_json(layout, inventory)
    from .family_profiles import write_family_report
    family = write_family_report(layout)
    return {
        "environment_lock": env_path,
        "node_schema": schema_path,
        "runtime": runtime,
        "family_status": family,
    }


def bootstrap(layout: GvdLayout | None = None) -> dict[str, Any]:
    layout = layout or GvdLayout.from_env()
    inventory = collect_inventory(layout=layout)
    paths = persist_inventory(layout, inventory)
    inventory["paths"] = {k: str(v) for k, v in paths.items()}
    family_path = paths.get("family_status")
    if family_path and Path(family_path).is_file():
        inventory["families"] = json.loads(Path(family_path).read_text(encoding="utf-8"))
    return inventory
