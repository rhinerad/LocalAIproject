@echo off
setlocal

rem This is a diagnostic-only Sideband profile. It deliberately does not use
rem the workstation LXMF bridge's identity or Reticulum configuration.
set "BASE=%~dp0"
set "EXE=%BASE%vendor_sideband_desktop\Sideband_2.0.1\Sideband.exe"
set "SIDEBAND_CONFIG=%BASE%runtime\sideband_desktop_diagnostic"
set "RNS_CONFIG=%BASE%runtime\rns_sideband_desktop_diagnostic"

if not exist "%EXE%" (
  echo Sideband.exe was not found at:
  echo %EXE%
  pause
  exit /b 1
)

rem One RNode can be owned by one program only. The bridge must be stopped
rem before configuring or testing that same PC-side Bluetooth/serial RNode
rem in the Sideband desktop app.
powershell.exe -NoProfile -Command "if (Get-CimInstance Win32_Process ^| Where-Object { $_.CommandLine -match 'lxmf_agent\.py' }) { exit 7 } else { exit 0 }"
if errorlevel 7 (
  echo.
  echo The Equal Shares LXMF bridge is running.
  echo Stop it before using Sideband Desktop with the same workstation RNode.
  echo This prevents two programs from competing for the Bluetooth/serial radio.
  echo.
  pause
  exit /b 7
)

if not exist "%SIDEBAND_CONFIG%" mkdir "%SIDEBAND_CONFIG%"
if not exist "%RNS_CONFIG%" mkdir "%RNS_CONFIG%"

start "Sideband Desktop Diagnostic" "%EXE%" --config "%SIDEBAND_CONFIG%" --rnsconfig "%RNS_CONFIG%"
endlocal
