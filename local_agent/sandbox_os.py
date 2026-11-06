#!/usr/bin/env python3
"""OS-enforced confinement for one run_code process on Windows.

The interpreter is started suspended, dropped to low integrity, and placed in
a job that allows one process and a memory cap. Low integrity is mandatory
integrity control: the process, and any descendant that somehow escaped the
job, cannot write a medium-integrity file. The job's active-process limit
is what stops a child interpreter from being created at all.

There is no unrestricted fallback. If any of these steps fail, the caller
must not launch the interpreter.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
from ctypes import wintypes
from pathlib import Path

CREATE_SUSPENDED = 0x00000004
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
TOKEN_ADJUST_DEFAULT = 0x0080
TOKEN_QUERY = 0x0008
TokenIntegrityLevel = 25
SE_GROUP_INTEGRITY = 0x20
SECURITY_MANDATORY_LOW_RID = 0x1000
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x00000008
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
WAIT_TIMEOUT = 0x00000102
STILL_ACTIVE = 259
INFINITE = 0xFFFFFFFF

DEFAULT_JOB_MEMORY = 1024 * 1024 * 1024

_KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
_ADVAPI = ctypes.WinDLL("advapi32", use_last_error=True)


class _SecurityAttributes(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _StartupInfo(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _ProcessInformation(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class _SidAndAttributes(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class _TokenMandatoryLabel(ctypes.Structure):
    _fields_ = [("Label", _SidAndAttributes)]


class _SidAuthority(ctypes.Structure):
    _fields_ = [("Value", ctypes.c_ubyte * 6)]


class _JobBasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [("Counter", ctypes.c_ulonglong * 6)]


class _JobExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JobBasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _check(ok, what: str):
    if not ok:
        err = ctypes.get_last_error()
        raise OSError(err, f"{what} failed (winerror {err})")


def _low_sid():
    authority = _SidAuthority((0, 0, 0, 0, 0, 16))
    sid = ctypes.c_void_p()
    _check(
        _ADVAPI.AllocateAndInitializeSid(
            ctypes.byref(authority), 1, SECURITY_MANDATORY_LOW_RID,
            0, 0, 0, 0, 0, 0, 0, ctypes.byref(sid),
        ),
        "AllocateAndInitializeSid",
    )
    return sid


def label_run_dir(run_dir: Path) -> None:
    """Mark the run directory low integrity so the confined process can write it."""
    proc = subprocess.run(
        ["icacls", str(run_dir), "/setintegritylevel", "(OI)(CI)L"],
        capture_output=True, text=True, timeout=15,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise OSError(f"could not label run directory low integrity: {detail}")


def sandbox_environment(run_dir: Path) -> dict[str, str]:
    """Environment for the interpreter. Parent secrets are not copied."""
    env: dict[str, str] = {}
    for key in ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "PATH"):
        value = os.environ.get(key)
        if value:
            env[key] = value
    run = str(run_dir)
    env.update({
        "TEMP": run,
        "TMP": run,
        "EQUAL_SHARES_SANDBOX_RUN": run,
        "EQUAL_SHARES_SANDBOX_NET": "0",
        "PYTHONUNBUFFERED": "1",
        "PYTHONUTF8": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "CUDA_VISIBLE_DEVICES": "-1",
        "NO_PROXY": "*",
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "http_proxy": "http://127.0.0.1:1",
        "https_proxy": "http://127.0.0.1:1",
    })
    return env


def _env_block(env: dict[str, str]) -> ctypes.Array:
    items = [f"{key}={value}" for key, value in env.items()]
    raw = ("\0".join(items) + "\0\0").encode("utf-16-le")
    buf = ctypes.create_string_buffer(raw)
    return buf


def _pipe() -> tuple[int, int]:
    read = wintypes.HANDLE()
    write = wintypes.HANDLE()
    sa = _SecurityAttributes()
    sa.nLength = ctypes.sizeof(sa)
    sa.bInheritHandle = True
    _check(_KERNEL.CreatePipe(ctypes.byref(read), ctypes.byref(write), ctypes.byref(sa), 0), "CreatePipe")
    return read.value, write.value


def _uninherit(handle: int) -> None:
    _check(_KERNEL.SetHandleInformation(handle, HANDLE_FLAG_INHERIT, 0), "SetHandleInformation")


def _read_all(handle: int) -> bytes:
    chunks: list[bytes] = []
    buf = ctypes.create_string_buffer(65536)
    got = wintypes.DWORD()
    while True:
        ok = _KERNEL.ReadFile(handle, buf, 65536, ctypes.byref(got), None)
        if not ok or got.value == 0:
            break
        chunks.append(buf.raw[: got.value])
    return b"".join(chunks)


def _close(handle: int | None) -> None:
    if handle:
        _KERNEL.CloseHandle(handle)


class ConfinedProcess:
    """Small stand-in for subprocess.Popen covering communicate, kill, and wait."""

    def __init__(self, pid: int, process: int, thread: int, job: int,
                 stdin_write: int, stdout_read: int, stderr_read: int, argv: list[str]):
        self.pid = pid
        self.returncode: int | None = None
        self.argv = argv
        self._process = process
        self._thread = thread
        self._job = job
        self._stdin_write = stdin_write
        self._stdout_read = stdout_read
        self._stderr_read = stderr_read
        self._closed = False

    def communicate(self, input=None, timeout=None):
        if input:
            data = input if isinstance(input, bytes) else str(input).encode("utf-8")
            written = wintypes.DWORD()
            _KERNEL.WriteFile(self._stdin_write, data, len(data), ctypes.byref(written), None)
        _close(self._stdin_write)
        self._stdin_write = 0
        out: dict[str, bytes] = {}

        def drain(name: str, handle: int) -> None:
            try:
                out[name] = _read_all(handle)
            except OSError:
                out[name] = b""

        threads = [
            threading.Thread(target=drain, args=("out", self._stdout_read), daemon=True),
            threading.Thread(target=drain, args=("err", self._stderr_read), daemon=True),
        ]
        for thread in threads:
            thread.start()
        millis = INFINITE if timeout is None else max(1, int(timeout * 1000))
        waited = _KERNEL.WaitForSingleObject(self._process, millis)
        if waited == WAIT_TIMEOUT:
            self.kill()
            _KERNEL.WaitForSingleObject(self._process, 5000)
            for thread in threads:
                thread.join(timeout=2)
            raise subprocess.TimeoutExpired(
                self.argv, timeout,
                output=out.get("out", b"").decode("utf-8", "replace"),
                stderr=out.get("err", b"").decode("utf-8", "replace"),
            )
        for thread in threads:
            thread.join(timeout=5)
        code = wintypes.DWORD()
        _KERNEL.GetExitCodeProcess(self._process, ctypes.byref(code))
        self.returncode = -1 if code.value == STILL_ACTIVE else int(code.value)
        return (
            out.get("out", b"").decode("utf-8", "replace"),
            out.get("err", b"").decode("utf-8", "replace"),
        )

    def kill(self) -> None:
        if self._job:
            _KERNEL.TerminateJobObject(self._job, 1)
        elif self._process:
            _KERNEL.TerminateProcess(self._process, 1)

    def wait(self, timeout=None):
        millis = INFINITE if timeout is None else max(0, int(timeout * 1000))
        _KERNEL.WaitForSingleObject(self._process, millis)
        code = wintypes.DWORD()
        _KERNEL.GetExitCodeProcess(self._process, ctypes.byref(code))
        if code.value != STILL_ACTIVE:
            self.returncode = int(code.value)
        return self.returncode

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close(self._stdin_write)
        _close(self._stdout_read)
        _close(self._stderr_read)
        _close(self._thread)
        _close(self._process)
        _close(self._job)
        self._stdin_write = self._stdout_read = self._stderr_read = 0
        self._thread = self._process = self._job = 0


def launch(argv: list[str], run_dir: Path, *, job_memory: int = DEFAULT_JOB_MEMORY) -> ConfinedProcess:
    """Start argv inside the run directory. Raises OSError if confinement fails."""
    if os.name != "nt":
        raise OSError("code execution requires a Windows integrity and job boundary")
    run_dir = Path(run_dir)
    label_run_dir(run_dir)
    env = sandbox_environment(run_dir)
    stdin_read, stdin_write = _pipe()
    stdout_read, stdout_write = _pipe()
    stderr_read, stderr_write = _pipe()
    _uninherit(stdin_write)
    _uninherit(stdout_read)
    _uninherit(stderr_read)
    process = thread = job = 0
    sid = None
    try:
        si = _StartupInfo()
        si.cb = ctypes.sizeof(si)
        si.dwFlags = STARTF_USESTDHANDLES
        si.hStdInput = stdin_read
        si.hStdOutput = stdout_write
        si.hStdError = stderr_write
        pi = _ProcessInformation()
        cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline(argv))
        env_buf = _env_block(env)
        flags = CREATE_SUSPENDED | CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | CREATE_UNICODE_ENVIRONMENT
        _check(
            _KERNEL.CreateProcessW(
                None, cmdline, None, None, True, flags, env_buf, str(run_dir),
                ctypes.byref(si), ctypes.byref(pi),
            ),
            "CreateProcessW",
        )
        process = pi.hProcess
        thread = pi.hThread
        _close(stdin_read)
        _close(stdout_write)
        _close(stderr_write)
        stdin_read = stdout_write = stderr_write = 0

        token = wintypes.HANDLE()
        _check(
            _ADVAPI.OpenProcessToken(process, TOKEN_ADJUST_DEFAULT | TOKEN_QUERY, ctypes.byref(token)),
            "OpenProcessToken",
        )
        try:
            sid = _low_sid()
            label = _TokenMandatoryLabel()
            label.Label.Sid = sid
            label.Label.Attributes = SE_GROUP_INTEGRITY
            _check(
                _ADVAPI.SetTokenInformation(
                    token, TokenIntegrityLevel, ctypes.byref(label), ctypes.sizeof(label),
                ),
                "SetTokenInformation",
            )
        finally:
            _close(token.value)

        job = _KERNEL.CreateJobObjectW(None, None)
        _check(job, "CreateJobObjectW")
        limits = _JobExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_ACTIVE_PROCESS
            | JOB_OBJECT_LIMIT_JOB_MEMORY
            | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        limits.BasicLimitInformation.ActiveProcessLimit = 1
        limits.JobMemoryLimit = int(job_memory)
        _check(
            _KERNEL.SetInformationJobObject(
                job, JobObjectExtendedLimitInformation,
                ctypes.byref(limits), ctypes.sizeof(limits),
            ),
            "SetInformationJobObject",
        )
        _check(_KERNEL.AssignProcessToJobObject(job, process), "AssignProcessToJobObject")
        _check(_KERNEL.ResumeThread(thread) != 0xFFFFFFFF, "ResumeThread")
        return ConfinedProcess(
            pid=int(pi.dwProcessId), process=process, thread=thread, job=job,
            stdin_write=stdin_write, stdout_read=stdout_read, stderr_read=stderr_read,
            argv=list(argv),
        )
    except Exception:
        if job:
            _KERNEL.TerminateJobObject(job, 1)
        elif process:
            _KERNEL.TerminateProcess(process, 1)
        _close(stdin_read)
        _close(stdin_write)
        _close(stdout_read)
        _close(stdout_write)
        _close(stderr_read)
        _close(stderr_write)
        _close(thread)
        _close(process)
        _close(job)
        raise
    finally:
        if sid:
            _ADVAPI.FreeSid(sid)


_KERNEL.CreatePipe.argtypes = [
    ctypes.POINTER(wintypes.HANDLE), ctypes.POINTER(wintypes.HANDLE),
    ctypes.POINTER(_SecurityAttributes), wintypes.DWORD,
]
_KERNEL.SetHandleInformation.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD]
_KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]
_KERNEL.ResumeThread.argtypes = [wintypes.HANDLE]
_KERNEL.ResumeThread.restype = wintypes.DWORD
_KERNEL.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_KERNEL.WaitForSingleObject.restype = wintypes.DWORD
_KERNEL.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
_KERNEL.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
_KERNEL.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
_KERNEL.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
_KERNEL.CreateJobObjectW.restype = wintypes.HANDLE
_KERNEL.SetInformationJobObject.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
]
_KERNEL.ReadFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]
_KERNEL.WriteFile.argtypes = [
    wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
]
_ADVAPI.OpenProcessToken.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
]
_ADVAPI.SetTokenInformation.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
]
_ADVAPI.FreeSid.argtypes = [ctypes.c_void_p]
