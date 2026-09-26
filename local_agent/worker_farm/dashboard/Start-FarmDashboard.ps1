<#
Starts the farm monitoring dashboard on loopback :8765 (default).

Uses system Python (not the farm venv). The page polls farm_status.json,
farm_health --json (via farm venv subprocess), and existing service checks.
Does not submit Celery jobs and does not reimplement Redis/Celery probes.

Bind default: 127.0.0.1 (matches Redis/relay discipline). Opt in to LAN
or the WireGuard hub with FARM_DASHBOARD_HOST, e.g.
  $env:FARM_DASHBOARD_HOST = '192.168.50.208'
  $env:FARM_DASHBOARD_HOST = '10.90.90.1'
Never 0.0.0.0. Also FARM_DASHBOARD_PORT.
#>
[CmdletBinding()]
param(
    [string]$HostAddress = $env:FARM_DASHBOARD_HOST,
    [int]$Port = $(if ($env:FARM_DASHBOARD_PORT) { [int]$env:FARM_DASHBOARD_PORT } else { 8765 })
)

$ErrorActionPreference = 'Stop'
$dashDir = Split-Path -Parent $PSCommandPath
$farmDir = Split-Path -Parent $dashDir
$repoRoot = Split-Path -Parent (Split-Path -Parent $farmDir)
$serverPy = Join-Path $dashDir 'server.py'

# Prefer install-dir system Python 3.12 over PATH venvs.
$systemPy = 'A:\Users\rhine\AppData\Local\Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $systemPy)) {
    $systemPy = (Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1).Source
}
if (-not $systemPy -or -not (Test-Path -LiteralPath $systemPy)) {
    throw "system Python not found"
}
if (-not (Test-Path -LiteralPath $serverPy)) {
    throw "server.py not found at $serverPy"
}

Write-Host "Repo: $repoRoot" -ForegroundColor DarkGray
Write-Host "Python: $systemPy" -ForegroundColor DarkGray
if ($HostAddress) {
    Write-Host "Starting farm dashboard (opt-in bind $HostAddress, port $Port)..." -ForegroundColor Cyan
} else {
    Write-Host "Starting farm dashboard (loopback 127.0.0.1, port $Port)..." -ForegroundColor Cyan
}

$argsList = @($serverPy)
if ($HostAddress) {
    $argsList += @('--host', $HostAddress)
}
if ($Port) {
    $argsList += @('--port', "$Port")
}

Set-Location -LiteralPath $repoRoot
& $systemPy @argsList