$ErrorActionPreference = 'Stop'

$Project = Split-Path -Parent $PSScriptRoot
$Python = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
$Runner = Join-Path $PSScriptRoot 'retry_narrator_audio_after_stage1.py'
$Runtime = Join-Path $Project 'outputs\equal_shares\runtime'
$Stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$Log = Join-Path $Runtime "narrator_repair_launcher_$Stamp.log"

Set-Location -LiteralPath $Project
"[$(Get-Date -Format o)] Queueing post-Stage-1 Narrator repair" |
    Add-Content -LiteralPath $Log -Encoding UTF8
& $Python $Runner 2>&1 | Tee-Object -FilePath $Log -Append
$ExitCode = $LASTEXITCODE
"[$(Get-Date -Format o)] Narrator repair coordinator exited $ExitCode" |
    Add-Content -LiteralPath $Log -Encoding UTF8
exit $ExitCode
