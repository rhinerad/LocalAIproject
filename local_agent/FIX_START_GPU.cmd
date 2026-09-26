@echo off
REM Starts the GPU Ollama server + ensures the 14B by running the CANONICAL launcher.
REM This is the real fix for "agent only uses CPU": it brings up :11434 with the 14B.
REM Safe: starts Ollama servers + the agent app. Never starts a render or ComfyUI.
cd /d "%~dp0"
echo Starting the canonical local-agent launcher (GPU + CPU Ollama, ensures 14B)...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0START_LOCAL_AGENT_GUI.ps1"
