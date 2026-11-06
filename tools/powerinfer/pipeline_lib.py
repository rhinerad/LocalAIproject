"""Shared helpers for the PowerInfer conversion pipeline. No GPU work on import."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
DEFAULT_EXTERNAL = REPO_ROOT / "external"
COMFY_PORT = 8188



def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_registry() -> dict[str, Any]:
    return json.loads((HERE / "models.json").read_text(encoding="utf-8"))


def target_config(model_id: str) -> dict[str, Any]:
    registry = load_registry()
    targets = registry["targets"]
    if model_id not in targets:
        known = ", ".join(sorted(targets))
        raise SystemExit(f"unknown model id {model_id!r}; known: {known}")
    cfg = dict(registry["defaults"])
    cfg.update(targets[model_id])
    cfg["model_id"] = model_id
    return cfg


def bundle_dir(vault: Path, model_id: str, build_id: str) -> Path:
    return vault / model_id / build_id


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def sha256_tree(root: Path, *, glob: str = "**/*") -> dict[str, Any]:
    files: list[dict[str, Any]] = []
    if not root.exists():
        return {"root": str(root), "count": 0, "combined_sha256": None, "files": []}
    for path in sorted(root.glob(glob)):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        files.append(
            {
                "path": rel,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    combined = hashlib.sha256()
    for item in files:
        combined.update(item["path"].encode("utf-8"))
        combined.update(b":")
        combined.update(item["sha256"].encode("utf-8"))
        combined.update(b"\n")
    return {
        "root": str(root),
        "count": len(files),
        "combined_sha256": combined.hexdigest() if files else None,
        "files": files,
    }


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def which_python(venv: Path | None = None) -> Path:
    if venv:
        candidate = venv / "Scripts" / "python.exe"
        if candidate.exists():
            return candidate
        candidate = venv / "bin" / "python"
        if candidate.exists():
            return candidate
    return Path(sys.executable)


def run(cmd: list[str] | list[Path], *, cwd: Path | None = None, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    rendered = [str(part) for part in cmd]
    print("+", " ".join(rendered), flush=True)
    completed = subprocess.run(
        rendered,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        check=False,
    )
    if check and completed.returncode != 0:
        raise SystemExit(f"command failed ({completed.returncode}): {' '.join(rendered)}")
    return completed


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket() as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def nvidia_smi(*args: str) -> subprocess.CompletedProcess[str] | None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        return None
    return subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def gpu_snapshot() -> dict[str, Any]:
    used = nvidia_smi("--query-gpu=name,memory.used,memory.total,memory.free", "--format=csv,noheader,nounits")
    procs = nvidia_smi("--query-compute-apps=pid,process_name,used_memory", "--format=csv,noheader")
    snapshot: dict[str, Any] = {
        "nvidia_smi": bool(used),
        "gpus": [],
        "compute_apps": [],
    }
    if used and used.returncode == 0:
        for line in used.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                snapshot["gpus"].append(
                    {
                        "name": parts[0],
                        "memory_used_mb": int(float(parts[1])),
                        "memory_total_mb": int(float(parts[2])),
                        "memory_free_mb": int(float(parts[3])),
                    }
                )
    if procs and procs.returncode == 0:
        for line in procs.stdout.splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                snapshot["compute_apps"].append(
                    {
                        "pid": parts[0],
                        "name": parts[1],
                        "used_memory": parts[2] if len(parts) > 2 else None,
                    }
                )
    return snapshot


def host_ram_snapshot() -> dict[str, Any]:
    try:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_uint64),
                ("ullAvailPhys", ctypes.c_uint64),
                ("ullTotalPageFile", ctypes.c_uint64),
                ("ullAvailPageFile", ctypes.c_uint64),
                ("ullTotalVirtual", ctypes.c_uint64),
                ("ullAvailVirtual", ctypes.c_uint64),
                ("ullAvailExtendedVirtual", ctypes.c_uint64),
            ]

        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            total = status.ullTotalPhys
            avail = status.ullAvailPhys
            return {
                "total_mb": round(total / (1024 * 1024), 1),
                "available_mb": round(avail / (1024 * 1024), 1),
                "used_mb": round((total - avail) / (1024 * 1024), 1),
                "load_percent": int(status.dwMemoryLoad),
            }
    except Exception:
        pass
    return {"total_mb": None, "available_mb": None, "used_mb": None, "load_percent": None}


def blocking_gpu_owners(snapshot: dict[str, Any] | None = None) -> list[str]:
    snapshot = snapshot or gpu_snapshot()
    owners: list[str] = []
    if port_open("127.0.0.1", COMFY_PORT):
        owners.append(f"comfyui-port-{COMFY_PORT}")
    for app in snapshot.get("compute_apps", []):
        name = str(app.get("name") or "").lower()
        if "comfy" in name or "stable-diffusion" in name:
            owners.append(app["name"])
    return owners


def relu_gate(source_dir: Path, expected_act: str = "relu") -> dict[str, Any]:
    config_path = source_dir / "config.json"
    if not config_path.is_file():
        raise SystemExit(f"missing {config_path}")
    config = read_json(config_path)
    act = str(config.get("hidden_act") or "").lower()
    model_type = str(config.get("model_type") or "")
    arch = config.get("architectures") or []
    fatrelu = act.startswith("fatrelu")
    ok = act == expected_act.lower() and not fatrelu
    return {
        "ok": ok,
        "config_path": str(config_path),
        "hidden_act": act,
        "model_type": model_type,
        "architectures": arch,
        "hidden_size": config.get("hidden_size"),
        "intermediate_size": config.get("intermediate_size"),
        "num_hidden_layers": config.get("num_hidden_layers"),
        "reason": None
        if ok
        else (
            "FATReLU is not supported by PowerInfer"
            if fatrelu
            else f"hidden_act={act!r} is not {expected_act!r}; ReLUfy before dump/train/convert"
        ),
    }


def percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 4)
    rank = (p / 100.0) * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return round(ordered[low] * (1 - weight) + ordered[high] * weight, 4)


def parse_powerinfer_logs(text: str) -> dict[str, Any]:
    flags = {
        "cuda_acceleration": "using CUDA for GPU acceleration" in text,
        "solver_invoked": "invoking powerinfer Python module" in text
        or "solver args:" in text,
        "gpu_idx_applied": "applying gpu_idx adapter" in text
        or "generated.gpuidx" in text,
        "activation_missing": "activation files under" in text and "not found" in text,
        "ffn_offload_line": None,
        "ffn_offloaded_mib": None,
        "sparse_pred_threshold": None,
        "vram_used_line": None,
    }
    for line in text.splitlines():
        if "llm_load_gpu_split: offloaded" in line:
            flags["ffn_offload_line"] = line.strip()
            match = re.search(r"offloaded\s+([0-9.]+)\s+MiB", line)
            if match:
                flags["ffn_offloaded_mib"] = float(match.group(1))
        if "sparse_pred_threshold" in line:
            flags["sparse_pred_threshold"] = line.strip()
        if "VRAM used:" in line:
            flags["vram_used_line"] = line.strip()
    # The first load invokes the solver; later loads correctly reuse the cached
    # .gpuidx adapter. Both paths are valid, but a 0-MiB result never is.
    flags["ffn_split_working"] = bool(
        flags["gpu_idx_applied"] and (flags["ffn_offloaded_mib"] or 0.0) > 0.0
    )
    return flags
