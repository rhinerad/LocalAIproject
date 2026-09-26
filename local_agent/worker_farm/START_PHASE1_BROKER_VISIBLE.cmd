@echo off
setlocal
title Equal Shares - Phase 1 Broker Diagnostics
echo.
echo === Phase 1 broker launcher started ===
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "& '%~dp0START_PHASE1_BROKER.ps1'; $code=$LASTEXITCODE; Write-Host ''; Write-Host ('=== Launcher finished; exit code: ' + $code + ' ===') -ForegroundColor Yellow"
echo.
echo This window stays open so you can read or copy any error above.
pause
