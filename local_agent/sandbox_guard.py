#!/usr/bin/env python3
"""In-process restrictions for one sandboxed Python run.

The OS job and integrity label in sandbox_os.py are the write and process
boundary. This guard still refuses reads outside the run directory (except
the interpreter install) and refuses to create another process, so a script
cannot hand work to an unrestricted child.
"""
from __future__ import annotations

import builtins
import io
import os
import runpy
import sys
from pathlib import Path


def _run_dir() -> Path:
    raw = os.environ.get("EQUAL_SHARES_SANDBOX_RUN", "")
    if not raw:
        raise SystemExit("sandbox guard: EQUAL_SHARES_SANDBOX_RUN is not set")
    return Path(raw).resolve()


def _interpreter_roots() -> tuple[Path, ...]:
    """Directories that hold the Python install itself (stdlib, venv libs).

    Import machinery and pathlib both reach the C-level file-open path that
    the audit hook below inspects, the same path a malicious script could use
    to read a project file. Reads have to be allowed somewhere outside
    run_dir or ordinary `import os`/`import json`/etc. inside the sandboxed
    script would break. Scope that allowance narrowly to the interpreter's
    own install roots — never the project tree, never arbitrary user paths —
    so imports work but a script still cannot read outside its run dir.
    """
    names = ("prefix", "exec_prefix", "base_prefix", "base_exec_prefix")
    roots = []
    for name in names:
        raw = getattr(sys, name, None)
        if raw:
            try:
                roots.append(Path(raw).resolve())
            except OSError:
                continue
    return tuple(dict.fromkeys(roots))


def _allowed(file, run_dir: Path, *, for_write: bool, interp_roots: tuple[Path, ...]) -> bool:
    if isinstance(file, int):
        return True
    if file is None:
        return False
    if hasattr(file, "fileno") and not isinstance(file, (str, bytes, os.PathLike)):
        return True
    try:
        raw = os.fsdecode(file)
    except (TypeError, ValueError):
        return False
    try:
        resolved = Path(raw).resolve()
    except OSError:
        return False
    try:
        resolved.relative_to(run_dir)
        return True
    except ValueError:
        pass
    if for_write:
        return False
    return any(_is_under(resolved, root) for root in interp_roots)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


_WRITE_MODE_CHARS = frozenset("wax+")


def _mode_is_write(mode) -> bool:
    if mode is None:
        return False
    if isinstance(mode, int):
        write_flags = (
            getattr(os, "O_WRONLY", 0) | getattr(os, "O_RDWR", 0)
            | getattr(os, "O_APPEND", 0) | getattr(os, "O_CREAT", 0)
            | getattr(os, "O_TRUNC", 0)
        )
        return bool(mode & write_flags)
    return any(ch in _WRITE_MODE_CHARS for ch in str(mode))


def _install(run_dir: Path) -> None:
    interp_roots = _interpreter_roots()
    orig_open = builtins.open
    orig_io_open = io.open
    orig_os_open = os.open
    orig_chdir = os.chdir

    def _refuse(file) -> None:
        raise PermissionError(f"sandbox: path is outside the run dir: {file!r}")

    def _open(file, mode="r", *args, **kwargs):
        if not _allowed(file, run_dir, for_write=_mode_is_write(mode), interp_roots=interp_roots):
            _refuse(file)
        return orig_open(file, mode, *args, **kwargs)

    def _io_open(file, mode="r", *args, **kwargs):
        if not _allowed(file, run_dir, for_write=_mode_is_write(mode), interp_roots=interp_roots):
            _refuse(file)
        return orig_io_open(file, mode, *args, **kwargs)

    def _os_open(path, flags, *args, **kwargs):
        if not _allowed(path, run_dir, for_write=_mode_is_write(flags), interp_roots=interp_roots):
            _refuse(path)
        return orig_os_open(path, flags, *args, **kwargs)

    def _chdir(path):
        if not _allowed(path, run_dir, for_write=True, interp_roots=interp_roots):
            _refuse(path)
        return orig_chdir(path)

    builtins.open = _open
    io.open = _io_open
    os.open = _os_open
    os.chdir = _chdir

    # Attribute monkeypatching above does not cover every path. pathlib's
    # accessor binds a direct reference to the original io.open at import
    # time (before this function ever runs), so Path.read_text/write_text/
    # open() reach the real io.open and skip _io_open entirely — confirmed:
    # a script doing Path(outside_file).read_text() reads it successfully
    # even with the patches above in place. CPython's C-level io.FileIO
    # constructor emits a "open" sys.audit event on every file open
    # regardless of which Python-level API reached it (builtins.open,
    # io.open, os.open, or pathlib), so hook that as the real enforcement
    # boundary; the monkeypatches above stay as defense-in-depth for
    # anything that does not go through io.FileIO. The import system also
    # opens files this way (reading .py/.pyc under the interpreter's own
    # install roots), which is why reads (never writes) are allowed there —
    # see _interpreter_roots().
    def _audit_hook(event: str, args: tuple) -> None:
        if event in {
            "subprocess.Popen", "os.system", "os.exec", "os.spawn",
            "os.posix_spawn", "os.startfile", "os.fork", "os.posix_fork",
        }:
            raise PermissionError("sandbox: process creation is disabled")
        if event in ("open", "os.open") and args:
            path = args[0]
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else None
            write = _mode_is_write(mode) or _mode_is_write(flags)
            if not _allowed(path, run_dir, for_write=write, interp_roots=interp_roots):
                _refuse(path)
        elif event == "os.chdir" and args:
            if not _allowed(args[0], run_dir, for_write=True, interp_roots=interp_roots):
                _refuse(args[0])

    sys.addaudithook(_audit_hook)

    if os.environ.get("EQUAL_SHARES_SANDBOX_NET") != "1":
        import socket

        def _blocked(*_a, **_k):
            raise OSError("sandbox: network is disabled")

        class _BlockedSocket:
            def __init__(self, *_a, **_k):
                raise OSError("sandbox: network is disabled")

        socket.socket = _BlockedSocket  # type: ignore[misc, assignment]
        socket.create_connection = _blocked  # type: ignore[assignment]
        if hasattr(socket, "create_server"):
            socket.create_server = _blocked  # type: ignore[assignment]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("sandbox guard: missing script path")
    run_dir = _run_dir()
    script = Path(sys.argv[1]).resolve()
    try:
        script.relative_to(run_dir)
    except ValueError as e:
        raise SystemExit(f"sandbox guard: script is outside the run dir: {script}") from e
    os.chdir(run_dir)
    sys.path.insert(0, str(run_dir))
    _install(run_dir)
    sys.argv = [str(script), *sys.argv[2:]]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
