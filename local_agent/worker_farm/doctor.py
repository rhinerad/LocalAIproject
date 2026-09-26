"""Read-only Phase 1 readiness report; never installs, starts, or exposes anything."""
from __future__ import annotations

import importlib.util
import os
import shutil
import socket
import subprocess
from pathlib import Path


HERE = Path(__file__).resolve().parent
REQUIRED_ENV = (
    "REDIS_PASSWORD", "FARM_BROKER_URL", "FARM_RESULT_BACKEND",
    "FARM_ROOT", "FARM_ENCRYPTION_KEY_B64",
)
WSL_DISTRO = "Ubuntu-24.04"
_VALID_ENGINES = ("desktop", "wsl")


def redis_engine() -> str:
    """Which Docker engine farm Redis launchers should use.

    FARM_REDIS_ENGINE=desktop|wsl. Unset/empty defaults to desktop (Docker
    Desktop) so existing operators are unchanged until Phase C.
    """
    raw = os.environ.get("FARM_REDIS_ENGINE")
    if raw is None or not str(raw).strip():
        return "desktop"
    value = str(raw).strip().lower()
    if value not in _VALID_ENGINES:
        raise ValueError(
            "FARM_REDIS_ENGINE must be 'desktop' or 'wsl' "
            f"(got {raw!r}); default is desktop"
        )
    return value


def docker_argv() -> list[str] | None:
    """CLI argv that talks to the selected engine's daemon (no extra args)."""
    engine = redis_engine()
    if engine == "wsl":
        wsl = shutil.which("wsl") or shutil.which("wsl.exe")
        if not wsl:
            return None
        return [wsl, "-d", WSL_DISTRO, "-e", "/usr/bin/docker"]
    found = shutil.which("docker")
    if found:
        return [found]
    candidate = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
    return [str(candidate)] if candidate.is_file() else None


def docker_path() -> str | None:
    """Find Docker even when a just-installed CLI has not refreshed PATH."""
    argv = docker_argv()
    return argv[0] if argv else None


def engine_status(executable: str | None = None) -> dict[str, object]:
    try:
        engine = redis_engine()
    except ValueError as exc:
        return {"installed": False, "ready": False, "engine": None,
                "detail": str(exc)}
    argv = docker_argv()
    if executable and engine == "desktop":
        argv = [executable]
    if not argv:
        detail = (
            "wsl.exe not found" if engine == "wsl" else "Docker CLI not found"
        )
        return {"installed": False, "ready": False, "engine": engine,
                "detail": detail}
    try:
        run = subprocess.run(
            [*argv, "version", "--format", "{{.Server.Version}}"],
            text=True, capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"installed": True, "ready": False, "engine": engine,
                "detail": f"engine probe failed: {type(exc).__name__}"}
    version = run.stdout.strip()
    if run.returncode == 0 and version:
        return {"installed": True, "ready": True, "engine": engine,
                "server_version": version}
    if engine == "wsl":
        detail = "Ubuntu-24.04 Docker CE unavailable"
    else:
        detail = "Docker engine unavailable for this Windows account"
    return {"installed": True, "ready": False, "engine": engine,
            "detail": detail}


def _parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def config_status(env_file: Path = HERE / ".env") -> dict[str, object]:
    values = _parse_env(env_file)
    if not values:
        return {"present": False, "valid": False, "detail": "missing .env"}
    missing = [key for key in REQUIRED_ENV if not values.get(key)]
    placeholders = any("CHANGE_ME" in values.get(key, "") for key in REQUIRED_ENV)
    broker = values.get("FARM_BROKER_URL", "")
    result = values.get("FARM_RESULT_BACKEND", "")
    aes_key = values.get("FARM_ENCRYPTION_KEY_B64", "")
    urls_ok = all(url.startswith("redis://:") and "@127.0.0.1:6379/" in url
                  for url in (broker, result))
    aes_ok = len(aes_key) == 44
    return {
        "present": True,
        "valid": not missing and not placeholders and urls_ok and aes_ok,
        "missing_fields": missing,
        "has_placeholders": placeholders,
        "aes_key_shape_valid": aes_ok,
        "loopback_broker_url": urls_ok,
    }


def broker_reachable() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 6379), timeout=1):
            return True
    except OSError:
        return False


def report() -> dict[str, object]:
    return {
        "celery_installed": bool(importlib.util.find_spec("celery")),
        "redis_client_installed": bool(importlib.util.find_spec("redis")),
        "cryptography_installed": bool(importlib.util.find_spec("cryptography")),
        "config": config_status(),
        "docker": engine_status(),
        "redis_loopback_reachable": broker_reachable(),
        "broker_binding": "127.0.0.1 only by checked-in compose.yaml",
        "remote_workers": "disabled until private encrypted overlay is configured",
    }


def main() -> int:
    status = report()
    for key, value in status.items():
        print(f"{key}: {value}")
    ready = all(status[key] for key in (
        "celery_installed", "redis_client_installed", "cryptography_installed",
        "redis_loopback_reachable",
    )) and status["config"]["valid"] and status["docker"]["ready"]
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
