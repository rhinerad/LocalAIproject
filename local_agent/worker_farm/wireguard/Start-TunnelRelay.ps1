<#
Starts the TCP relay that forwards WireGuard-tunneled connections to Redis.
Run on the workstation, only while a secondary worker session is active.
The relay is NOT started automatically; it must be stopped between sessions.

The relay binds to 10.90.90.1 (the WireGuard hub interface IP) and forwards
raw bytes to 127.0.0.1:6379 where Redis already listens.
It is plumbing, not a security boundary -- see relay\tunnel_relay.py for details.

Requires: WireGuard hub service is running, local_agent/worker_farm/.venv exists.
Stop with Ctrl-C. Each secondary worker session needs a fresh relay start.
#>
[CmdletBinding()]
param(
    [string]$BindIp   = '10.90.90.1',
    [int]   $BindPort = 6379
)

$ErrorActionPreference = 'Stop'
$farmDir  = Split-Path -Parent $PSCommandPath | Split-Path -Parent
$relayPy  = Join-Path $farmDir 'relay\tunnel_relay.py'
$venv     = Join-Path $farmDir '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $relayPy)) {
    throw "relay\tunnel_relay.py not found at $relayPy."
}
if (-not (Test-Path -LiteralPath $venv)) {
    throw ".venv not found at $venv. Run local_agent/worker_farm/requirements.txt install first."
}

# Sanity-check that the WireGuard interface is up
$wg = 'C:\Program Files\WireGuard\wg.exe'
if (Test-Path -LiteralPath $wg) {
    $check = & $wg show hub 2>&1
    if ($LASTEXITCODE -ne 0 -or "$check" -notmatch 'interface') {
        Write-Warning "WireGuard 'hub' interface does not appear to be up. Start Install-WireGuardHubService.ps1 first."
    }
}

Write-Host "Starting tunnel relay: $BindIp`:$BindPort -> 127.0.0.1:6379" -ForegroundColor Cyan
Write-Host "Press Ctrl-C to stop." -ForegroundColor Yellow
Write-Host ""
& $venv $relayPy --bind-ip $BindIp --bind-port $BindPort
