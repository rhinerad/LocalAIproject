@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%START_SIDEBAND_BRIDGE.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
  echo.
  echo The Sideband bridge did not start. The message above explains why.
  pause
)
exit /b %EXIT_CODE%
