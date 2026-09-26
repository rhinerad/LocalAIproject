@echo off
setlocal EnableExtensions
set PYTHONUNBUFFERED=1
set REPO=A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09
set RUNTIME=%REPO%\local_agent\worker_farm\runtime
set MARKER=%RUNTIME%\farm_dashboard_task_run.log
set LOG=%RUNTIME%\farm_dashboard.log
set PS1=%REPO%\local_agent\worker_farm\dashboard\Start-FarmDashboard.ps1
if not exist "%RUNTIME%" mkdir "%RUNTIME%"
echo START %DATE% %TIME% session=%SESSIONNAME% > "%MARKER%"
whoami >> "%MARKER%" 2>&1
echo cd_before=%CD% >> "%MARKER%"
cd /d "%REPO%"
echo cd_after=%CD% >> "%MARKER%"
if exist "%PS1%" (echo SCRIPT_OK>>"%MARKER%") else (echo SCRIPT_MISSING>>"%MARKER%")
echo launching>>"%MARKER%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%PS1%" >> "%LOG%" 2>&1
call set RC=%ERRORLEVEL%
echo END rc=%RC% %DATE% %TIME% session=%SESSIONNAME% >> "%MARKER%"
exit /b %RC%
