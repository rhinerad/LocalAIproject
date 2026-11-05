$ErrorActionPreference = 'Stop'
$Script = Join-Path $PSScriptRoot 'equal_shares_activity_watchdog.ps1'
$Owner = Join-Path (Split-Path -Parent $PSScriptRoot) 'outputs\equal_shares\runtime\activity_watchdog_owner.json'

if (Test-Path -LiteralPath $Owner) {
    try {
        $Record = Get-Content -LiteralPath $Owner -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([int]$Record.pid -gt 0 -and (Get-Process -Id ([int]$Record.pid) -ErrorAction SilentlyContinue)) {
            Write-Output "Watchdog already live at PID $($Record.pid)."
            exit 0
        }
    } catch {}
}

$Process = Start-Process -FilePath 'powershell.exe' -ArgumentList @(
    '-NoLogo', '-ExecutionPolicy', 'Bypass', '-File', $Script
) -WindowStyle Hidden -PassThru
Write-Output "Started Equal Shares activity watchdog at PID $($Process.Id)."

