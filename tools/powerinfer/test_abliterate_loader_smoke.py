"""Bounded subprocess smoke for the streaming TurboSparse loader.

Hard-kills the child if it exceeds the wall clock. Does not write a checkpoint
and does not touch the source snapshot.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = Path(
    r"A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09\.venv-ablit\Scripts\python.exe"
)
TIMEOUT_S = 180


def test_math_subprocess() -> None:
    exe = str(PY if PY.is_file() else sys.executable)
    proc = subprocess.run(
        [exe, str(HERE / "test_abliterate_projected_math.py")],
        cwd=str(HERE),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "math-ok" in proc.stdout


def test_v2_smoke_subprocess() -> None:
    exe = str(PY if PY.is_file() else sys.executable)
    proc = subprocess.run(
        [
            exe,
            str(HERE / "abliterate_turbosparse_v2.py"),
            "--smoke",
            "--trust-remote-code",
            "--max-seconds",
            str(TIMEOUT_S),
        ],
        cwd=str(HERE),
        capture_output=True,
        text=True,
        timeout=TIMEOUT_S + 15,
        check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"smoke failed rc={proc.returncode}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
    assert '"status": "smoke-ok"' in proc.stdout
    assert '"wrote_checkpoint": false' in proc.stdout.lower() or '"wrote_checkpoint": False' in proc.stdout


if __name__ == "__main__":
    test_math_subprocess()
    print("math-subprocess-ok", flush=True)
    test_v2_smoke_subprocess()
    print("v2-smoke-ok", flush=True)
