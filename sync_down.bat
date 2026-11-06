@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_down.ps1" %*
