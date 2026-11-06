<#
Installs hub.conf as a Windows WireGuard tunnel service named 'hub'.
Must be run as Administrator. hub.conf must exist (Generate-HubKeypair.ps1).

The Windows WireGuard client creates a service named WireGuardTunnel$hub.
The tunnel interface name (visible in wg show, ipconfig) is 'hub'.

To uninstall:  wireguard /uninstalltunnelservice hub
To stop only:  Stop-Service 'WireGuardTunnel$hub'
To start:      Start-Service 'WireGuardTunnel$hub'
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here      = Split-Path -Parent $PSCommandPath
$wireguard = 'C:\Program Files\WireGuard\wireguard.exe'
$wg        = 'C:\Program Files\WireGuard\wg.exe'
$hubConf   = Join-Path $here 'hub.conf'
$svcName   = 'WireGuardTunnel$hub'

if (-not (Test-Path -LiteralPath $wireguard)) {
    throw "WireGuard not found at '$wireguard'. Install from https://www.wireguard.com/install/ first."
}
if (-not (Test-Path -LiteralPath $hubConf)) {
    throw "hub.conf not found. Run Generate-HubKeypair.ps1 first."
}
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must run as Administrator (right-click -> Run as Administrator)."
}

$existing = Get-Service -Name $svcName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Service '$svcName' already exists (status: $($existing.Status))." -ForegroundColor Yellow
    Write-Host "Nothing installed. To reinstall: wireguard /uninstalltunnelservice hub, then re-run." -ForegroundColor Yellow
    return
}

Write-Host "Installing WireGuard tunnel service from: $hubConf" -ForegroundColor Cyan
& $wireguard /installtunnelservice $hubConf
if ($LASTEXITCODE -ne 0) {
    throw "wireguard /installtunnelservice exited $LASTEXITCODE. Verify hub.conf is valid."
}

# Give the service a moment to start
Start-Sleep -Seconds 3
$svc = Get-Service -Name $svcName -ErrorAction SilentlyContinue
$statusText = if ($svc) { $svc.Status } else { 'not found' }
$color = if ($svc -and $svc.Status -eq 'Running') { 'Green' } else { 'Yellow' }
Write-Host "Service status: $statusText" -ForegroundColor $color

if (Test-Path -LiteralPath $wg) {
    Write-Host ""
    Write-Host "=== wg show hub ===" -ForegroundColor Cyan
    & $wg show hub 2>&1
}

Write-Host ""
Write-Host "The hub interface is 10.90.90.1/28, listening on UDP 51820." -ForegroundColor Green
Write-Host "Next: for each secondary machine, run Add-WireGuardPeer.ps1 with that machine's public key."
Write-Host "After peers are added, run Test-TunnelConnectivity.ps1."
