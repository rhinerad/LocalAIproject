@echo off
REM Runs the GPU-routing diagnosis and writes the result to a file Claude can read.
REM Safe: only observes ports / VRAM / Ollama and runs router.py. Never touches a render.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0DIAGNOSE_GPU_ROUTING.ps1" > "%~dp0gpu_diag_result.txt" 2>&1
echo Done. Result written to gpu_diag_result.txt
