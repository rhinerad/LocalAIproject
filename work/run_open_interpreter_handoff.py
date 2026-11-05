#!/usr/bin/env python3
"""Run the Equal Shares handoff through Open Interpreter with CPU-only Ollama."""

from pathlib import Path
import os
import platform
import subprocess
import traceback

# Python 3.12's platform.system() can hang in a WMI query on this Windows
# installation. Open Interpreter imports Blessed, which calls it at startup.
# Supply the known local platform values so startup does not depend on WMI.
platform.system = lambda: "Windows"
platform.release = lambda: "10"
platform.version = lambda: "10.0"
platform.machine = lambda: "AMD64"
platform.processor = lambda: ""

ROOT = Path(__file__).resolve().parents[1]
HANDOFF = ROOT / "COMFYUI_STORY_HANDOFF_2026-08-09"
NOTEBOOK_STATE = HANDOFF / "open_interpreter_runtime"
NOTEBOOK_STATE.mkdir(parents=True, exist_ok=True)
for variable, folder in {
    "IPYTHONDIR": "ipython",
    "JUPYTER_CONFIG_DIR": "jupyter_config",
    "JUPYTER_DATA_DIR": "jupyter_data",
    "JUPYTER_RUNTIME_DIR": "jupyter_runtime",
}.items():
    directory = NOTEBOOK_STATE / folder
    directory.mkdir(parents=True, exist_ok=True)
    os.environ[variable] = str(directory)

from interpreter import interpreter
from interpreter.core.computer.terminal.base_language import BaseLanguage


class DirectPowerShell(BaseLanguage):
    """Execute each agent code block as a complete PowerShell script.

    The Open Interpreter version installed on this machine feeds multiline
    try/catch blocks into an interactive PowerShell process. Windows can leave
    that process at the ``>>`` continuation prompt forever. A fresh
    non-interactive process treats stdin as one complete script and returns a
    definite exit code instead.
    """

    name = "PowerShell"
    file_extension = "ps1"
    # Local coding models frequently label Windows command blocks as ``sh`` or
    # ``bash`` even when the command itself is PowerShell-compatible. Route
    # those labels through this same native Windows executor instead of letting
    # Open Interpreter reject the block as an unavailable language.
    aliases = ["powershell", "ps1", "sh", "shell", "bash", "cmd"]

    def __init__(self):
        self.process = None

    def run(self, code):
        prefix = (
            "$ErrorActionPreference = 'Stop'\n"
            "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n"
            "$OutputEncoding = [Console]::OutputEncoding\n"
            f"Set-Location -LiteralPath '{HANDOFF}'\n"
        )
        try:
            self.process = subprocess.Popen(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    "-",
                ],
                cwd=str(HANDOFF),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            stdout, stderr = self.process.communicate(prefix + code + "\n")
            if stdout:
                yield {"type": "console", "format": "output", "content": stdout}
            if stderr:
                yield {"type": "console", "format": "output", "content": stderr}
            if self.process.returncode:
                yield {
                    "type": "console",
                    "format": "output",
                    "content": f"PowerShell exited with code {self.process.returncode}.\n",
                }
        except Exception:
            yield {
                "type": "console",
                "format": "output",
                "content": traceback.format_exc(),
            }
        finally:
            self.process = None

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()

    def terminate(self):
        self.stop()


PROMPT = (HANDOFF / "OPEN_INTERPRETER_OMNI_START_PROMPT.txt").read_text(encoding="utf-8-sig")

original_completions = interpreter.llm.completions


def cpu_only_completions(**params):
    params["num_gpu"] = 0
    params["num_thread"] = 4
    # Four of the host's 16 logical processors keeps the offline agent useful
    # without sustaining the roughly 50% package load observed at the default.
    params["num_thread"] = 4
    return original_completions(**params)


interpreter.llm.completions = cpu_only_completions
interpreter.llm.model = "ollama/qwen2.5-coder:14b"
interpreter.llm.api_base = "http://127.0.0.1:11434"
interpreter.llm.context_window = 32768
interpreter.llm.max_tokens = 2048
# Keep execution on the native Windows command runner. The bundled Python
# notebook layer is unreliable on this machine and is unnecessary here.
interpreter.computer.languages = [DirectPowerShell]
interpreter.auto_run = True
interpreter.safe_mode = "off"
interpreter.disable_telemetry = True
interpreter.in_terminal_interface = True
interpreter.plain_text_display = True

interpreter.chat(PROMPT, display=True)
