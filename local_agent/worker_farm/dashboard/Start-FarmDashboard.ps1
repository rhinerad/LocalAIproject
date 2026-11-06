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

# System Python resolution, portable across workstations (no hard-coded
# install path): FARM_DASHBOARD_PYTHON, then the `py -3` launcher, then
# `python` on PATH. The dashboard is stdlib-only, so any CPython 3 works.
function Resolve-DashboardPython {
    if (-not [string]::IsNullOrWhiteSpace($env:FARM_DASHBOARD_PYTHON) -and
        (Test-Path -LiteralPath $env:FARM_DASHBOARD_PYTHON)) {
        return $env:FARM_DASHBOARD_PYTHON
    }
    $py = Get-Command py.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($py) {
        try {
            $resolved = (& $py.Source -3 -c 'import sys; print(sys.executable)' 2>$null | Select-Object -First 1)
            if ($LASTEXITCODE -eq 0 -and $resolved -and (Test-Path -LiteralPath $resolved.Trim())) {
                return $resolved.Trim()
            }
        } catch { }
    }
    $onPath = Get-Command python -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($onPath -and (Test-Path -LiteralPath $onPath.Source)) {
        return $onPath.Source
    }
    return $null
}

$systemPy = Resolve-DashboardPython
if (-not $systemPy) {
    throw "system Python not found: set FARM_DASHBOARD_PYTHON, install the py launcher, or put python on PATH"
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