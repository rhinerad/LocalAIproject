$ErrorActionPreference = 'Stop'

$Project = Split-Path -Parent $PSScriptRoot
$Python = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = Join-Path $PSScriptRoot 'continue_audio_generation_nonblocking.py'
$Runtime = Join-Path $Project 'outputs\equal_shares\runtime'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Log = Join-Path $Runtime "audio_nonblocking_launcher_$Stamp.log"

Set-Location -LiteralPath $Project
"[$(Get-Date -Format o)] Starting nonblocking Stage-1 audio continuation" |
    Add-Content -LiteralPath $Log -Encoding UTF8
& $Python $Runner 2>&1 | Tee-Object -FilePath $Log -Append
$ExitCode = $LASTEXITCODE
"[$(Get-Date -Format o)] Nonblocking audio continuation exited $ExitCode" |
    Add-Content -LiteralPath $Log -Encoding UTF8
exit $ExitCode
