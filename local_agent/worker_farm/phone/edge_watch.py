"""Private Termux watcher. The Download request file is a trigger, not code."""
from __future__ import annotations

import hashlib
import os
import pathlib
import subprocess
import threading
import time

HOME = pathlib.Path(os.environ.get("HOME", "/data/data/com.termux/files/home"))
EDGE = HOME / "powerinfer-edge"
BOOT = EDGE / "edge_boot.py"
MANIFEST = EDGE / "MANIFEST.sha256"
LOG = EDGE / "edge_watch.log"
REQ = pathlib.Path("/sdcard/Download/edge_launch_request.txt")
LOG_CAP = 65536


def _log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > LOG_CAP:
        LOG.write_text("", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")


def _verify_manifest() -> None:
    if not MANIFEST.is_file():
        raise RuntimeError("private manifest is missing")
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        name = name.strip()
        if "/" in name or "\\" in name or name.startswith("."):
            raise RuntimeError("manifest entry refused")
        path = EDGE / name
        got = hashlib.sha256(path.read_bytes()).hexdigest()
        if got != digest.lower():
            raise RuntimeError(f"hash mismatch: {name}")


def _run_capped(cmd: list[str], timeout: int) -> tuple[int, str, str]:
    proc = subprocess.Popen(
        cmd, cwd=str(EDGE), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    boxes: dict[str, list[str]] = {"out": [], "err": []}

    def _cap(pipe, key: str) -> None:
        chunk = pipe.read(8001) if pipe is not None else ""
        if chunk and len(chunk) > 8000:
            try:
                proc.kill()
            except OSError:
                pass
        boxes[key].append((chunk or "")[:8000])

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
    code = proc.returncode if proc.returncode is not None else 1
    return code, boxes["out"][0] if boxes["out"] else "", boxes["err"][0] if boxes["err"] else ""


def main() -> None:
    _log("watcher start")
    last = ""
    while True:
        try:
            if REQ.is_file():
                text = REQ.read_text(encoding="utf-8", errors="replace").strip().splitlines()
                stamp = text[1] if len(text) > 1 else (text[0] if text else "")
                if stamp and stamp != last:
                    last = stamp
                    _verify_manifest()
                    _log("launch private boot")
                    code, out, err = _run_capped(["python", str(BOOT)], timeout=1200)
                    _log(f"exit={code}")
                    if out:
                        _log("stdout:" + out.replace("\n", " | "))
                    if err:
                        _log("stderr:" + err.replace("\n", " | "))
        except Exception as exc:
            _log(f"err:{type(exc).__name__}:{exc}")
        time.sleep(2)


if __name__ == "__main__":
    main()
