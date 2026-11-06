@echo off
setlocal
set "SCRIPT=%~dp0START_TURBOSPARSE_OVERNIGHT.ps1"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
set "RESULT=%ERRORLEVEL%"
echo.
echo Overnight TurboSparse runner finished with exit code %RESULT%.
exit /b %RESULT%
