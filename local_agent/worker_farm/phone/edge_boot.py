"""One private edge launch. Shared storage is not on the execution path."""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import threading

HOME = pathlib.Path(os.environ.get("HOME", "/data/data/com.termux/files/home"))
EDGE = HOME / "powerinfer-edge"
CONF = HOME / ".config" / "local-agent"
ENV_FILE = CONF / "launcher.env"


def _load_env() -> dict[str, str]:
    if not ENV_FILE.is_file():
        raise SystemExit("private launcher.env is missing")
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _pin(path: pathlib.Path, pin: pathlib.Path) -> None:
    if not pin.is_file():
        raise SystemExit(f"pin missing for {path.name}")
    expected = pin.read_text(encoding="utf-8").strip().lower()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected:
        raise SystemExit(f"pin mismatch for {path.name}")


def _chmod(path: pathlib.Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError as exc:
        raise SystemExit(f"chmod failed for {path}") from exc


def _run_capped(cmd: list[str], env: dict[str, str], cwd: str, timeout: int) -> int:
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    captured: dict[str, str] = {"out": "", "err": ""}

    def _cap(pipe, key: str) -> None:
        chunk = pipe.read(8001) if pipe is not None else ""
        if chunk and len(chunk) > 8000:
            try:
                proc.kill()
            except OSError:
                pass
        captured[key] = (chunk or "")[:8000]

    threads = (
        threading.Thread(target=_cap, args=(proc.stdout, "out")),
        threading.Thread(target=_cap, args=(proc.stderr, "err")),
    )
    for thread in threads:
        thread.start()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
    for thread in threads:
        thread.join(timeout=5)
    log = EDGE / "edge_boot_run.txt"
    log.write_text(captured["out"] + captured["err"], encoding="utf-8")
    _chmod(log, 0o600)
    return proc.returncode if proc.returncode is not None else 1


def main() -> int:
    cfg = _load_env()
    runtime = cfg.get("EDGE_RUNTIME", "pwri").strip().lower()
    gateway = cfg.get("EDGE_GATEWAY", "https://10.90.91.1:8743").rstrip("/")
    if gateway != "https://10.90.91.1:8743":
        raise SystemExit("launcher gateway must be the overlay address")
    timeout = cfg.get("EDGE_TIMEOUT", "900")
    threads = cfg.get("EDGE_THREADS", "4")
    _chmod(CONF, 0o700)
    _chmod(EDGE, 0o700)
    for name in ("edge-token", "client.key.pem", "client.cert.pem", "ca.cert.pem"):
        path = CONF / name
        if path.is_file():
            _chmod(path, 0o600)
    worker = EDGE / "termux_powerinfer2_edge_worker.py"
    if not worker.is_file():
        raise SystemExit("private worker is missing")
    _chmod(worker, 0o600)
    if runtime == "pwri":
        binary = pathlib.Path(cfg.get("EDGE_BINARY", str(EDGE / "powerinfer-main")))
        model = pathlib.Path(cfg.get(
            "EDGE_MODEL", str(EDGE / "models" / "relu-llama-7b.q4.powerinfer.gguf"),
        ))
        os.environ["EDGE_USE_CLASSIC_POWERINFER"] = "1"
        os.environ.pop("EDGE_USE_STOCK_LLAMA", None)
    else:
        binary = pathlib.Path(cfg.get(
            "EDGE_BINARY", "/data/data/com.termux/files/usr/bin/llama-completion",
        ))
        model = pathlib.Path(cfg.get(
            "EDGE_MODEL", str(EDGE / "models" / "Llama-3.2-1B-Instruct-Q4_K_M.gguf"),
        ))
        os.environ["EDGE_USE_STOCK_LLAMA"] = "1"
        os.environ.pop("EDGE_USE_CLASSIC_POWERINFER", None)
    _pin(binary, EDGE / f"{binary.name}.sha256")
    _pin(model, EDGE / f"{model.name}.sha256")
    if not binary.is_file() or not model.is_file():
        raise SystemExit("pinned runtime files are missing")
    if runtime == "pwri":
        _chmod(binary, 0o755)
    env = os.environ.copy()
    env.pop("LD_LIBRARY_PATH", None)
    env.pop("EDGE_SSL_NO_HOSTNAME", None)
    env.pop("EDGE_ALLOW_LOOPBACK", None)
    cmd = [
        "python", str(worker),
        "--gateway", gateway,
        "--token-file", str(CONF / "edge-token"),
        "--binary", str(binary),
        "--model", str(model),
        "--once",
        "--timeout", timeout,
        "--threads", threads,
    ]
    return _run_capped(cmd, env, str(EDGE), timeout=int(timeout) + 30)


if __name__ == "__main__":
    raise SystemExit(main())
