#!/usr/bin/env python3
"""Isolated, bounded code execution for the local agent's run_code tool.

Runs live only inside local_agent/sandbox/run_<id>/. The interpreter is
confined with sandbox_os: low integrity, a one-process job, and a memory cap.
Network stays off. CPU only. There is no unrestricted fallback.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import sandbox_os

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EQ = ROOT / "outputs" / "equal_shares"
SANDBOX_ROOT = HERE / "sandbox"
GUARD = HERE / "sandbox_guard.py"
PY = sys.executable or "python"

DEFAULT_TIMEOUT = 30
MAX_TIMEOUT = 120
MAX_OUTPUT_CHARS = 16000
MAX_CODE_BYTES = 200_000
KEEP_RUNS = 32

LANGUAGES = {
    "python": "python",
    "py": "python",
    "javascript": "node",
    "js": "node",
    "node": "node",
}


class SandboxError(ValueError):
    pass


def sandbox_root() -> Path:
    SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    return SANDBOX_ROOT.resolve()


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (ValueError, OSError):
        return False


def run_dir_of(path: Path) -> Path | None:
    try:
        rel = path.resolve().relative_to(sandbox_root())
    except (ValueError, OSError):
        return None
    if not rel.parts or not str(rel.parts[0]).startswith("run_"):
        return None
    return (sandbox_root() / rel.parts[0]).resolve()


def is_sandbox_file(path: Path) -> bool:
    run = run_dir_of(path)
    if run is None:
        return False
    resolved = path.resolve()
    return resolved != run and _is_under(resolved, run)


def new_run_dir() -> Path:
    d = sandbox_root() / f"run_{uuid.uuid4().hex[:12]}"
    d.mkdir(parents=True, exist_ok=False)
    return d


def prune_sandbox(keep: int = KEEP_RUNS) -> None:
    """Delete oldest run_* dirs. Never touches anything outside sandbox/."""
    root = sandbox_root()
    runs = [p for p in root.iterdir() if p.is_dir() and p.name.startswith("run_")]
    runs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in runs[keep:]:
        if _is_under(old, root) and old.resolve() != root:
            shutil.rmtree(old, ignore_errors=True)


def _resolve_sandbox_path(raw: str) -> Path:
    text = str(raw or "").strip()
    if not text:
        raise SandboxError("path is required")
    p = Path(text)
    candidates: list[Path] = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(HERE / p)
        candidates.append(ROOT / p)
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if _is_under(resolved, EQ):
            raise SandboxError("path is outside the sandbox")
        if is_sandbox_file(resolved):
            return resolved
    raise SandboxError(f"path is outside the sandbox: {text}")


def _interpreter(kind: str) -> list[str]:
    if kind == "python":
        if not GUARD.is_file():
            raise SandboxError("sandbox guard is missing")
        return [PY, "-I", "-B", str(GUARD)]
    if kind == "node":
        exe = shutil.which("node")
        if not exe:
            raise SandboxError("node is not on PATH")
        # The run directory is filled in by _node_argv once it exists.
        return [exe, "--no-warnings", "--permission"]
    raise SandboxError(f"unsupported language {kind!r}")


def _cap(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    if text is None:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n[truncated at {limit} of {len(text)} chars]"


def _node_argv(argv: list[str], run_dir: Path) -> list[str]:
    """Grant Node filesystem access only inside the run directory."""
    if "--permission" not in argv:
        return argv
    run = str(run_dir)
    extra = [f"--allow-fs-read={run}", f"--allow-fs-write={run}"]
    head = [argv[0], "--no-warnings", "--permission", *extra]
    return head + [arg for arg in argv[1:] if arg != "--no-warnings" and arg != "--permission"]


def run_code(args: dict) -> str:
    language = str(args.get("language") or "python").strip().lower()
    kind = LANGUAGES.get(language)
    if kind is None:
        raise SandboxError(
            f"unsupported language {language!r}; allowed: {sorted(set(LANGUAGES))}")
    raw_path = str(args.get("path") or "").strip()
    code = args.get("code")
    if code is not None and not isinstance(code, str):
        raise SandboxError("code must be a string")
    if not raw_path and code is None:
        raise SandboxError("code or path is required")
    if code is not None and len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise SandboxError(f"code exceeds {MAX_CODE_BYTES} bytes")

    timeout = args.get("timeout", DEFAULT_TIMEOUT)
    try:
        timeout = int(timeout)
    except (TypeError, ValueError) as e:
        raise SandboxError("timeout must be an integer") from e
    timeout = max(1, min(timeout, MAX_TIMEOUT))
    allow_network = bool(args.get("allow_network", False))
    if allow_network:
        raise SandboxError(
            "allow_network is refused; code execution has no OS network boundary")
    stdin = args.get("stdin")
    if stdin is None:
        stdin_data = None
    else:
        stdin_data = str(stdin)

    if raw_path:
        script = _resolve_sandbox_path(raw_path)
        if not script.is_file():
            raise SandboxError(f"{script} is not a file")
        run_dir = run_dir_of(script)
        if run_dir is None:
            raise SandboxError("path is outside the sandbox")
        if code is not None:
            script.write_text(code, encoding="utf-8")
    else:
        run_dir = new_run_dir()
        name = "main.py" if kind == "python" else "main.js"
        script = run_dir / name
        script.write_text(code or "", encoding="utf-8")

    prune_sandbox()

    argv = _node_argv(_interpreter(kind), run_dir) + [str(script)]
    started = time.monotonic()
    timed_out = False
    exit_code = -1
    stdout = ""
    stderr = ""
    try:
        proc = sandbox_os.launch(argv, run_dir)
    except OSError as e:
        raise SandboxError(f"could not start a confined interpreter: {e}") from e
    try:
        out, err = proc.communicate(stdin_data, timeout=timeout)
        stdout, stderr = out or "", err or ""
        exit_code = int(proc.returncode)
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        proc.kill()
        stdout = exc.output or ""
        stderr = exc.stderr or ""
        exit_code = -1
        if stderr:
            stderr += "\n"
        stderr += f"sandbox: timed out after {timeout}s and the process group was killed"
    finally:
        closer = getattr(proc, "close", None)
        if closer is not None:
            closer()
    duration = round(time.monotonic() - started, 4)
    result = {
        "stdout": _cap(stdout),
        "stderr": _cap(stderr),
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration": duration,
        "run_dir": str(run_dir),
        "allow_network": allow_network,
        "language": kind,
    }
    if allow_network:
        result["note"] = "allow_network=true was requested; Windows network isolation is best-effort"
    return json.dumps(result)
