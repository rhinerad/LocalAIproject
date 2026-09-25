@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_up.ps1" %*
