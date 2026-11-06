# Elevated installer for the isolated 10.90.91.0/30 overlay only.
# Never touches worker_farm/wireguard/hub.conf or WireGuardTunnel$hub.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$log = Join-Path $PSScriptRoot 'runtime\wireguard\install.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
function Log([string]$m) {
    $line = '{0:o} {1}' -f (Get-Date).ToUniversalTime(), $m
    Add-Content -Path $log -Value $line
    Write-Output $line
}
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Log 'not elevated'
    throw 'must run as Administrator'
}
$wireguard = 'C:\Program Files\WireGuard\wireguard.exe'
$conf = Join-Path $PSScriptRoot 'runtime\wireguard\edge-phone.conf'
if (-not (Test-Path -LiteralPath $conf)) { throw "missing $conf" }
$svc = 'WireGuardTunnel$edge-phone'
$existing = Get-Service -Name $svc -ErrorAction SilentlyContinue
if ($existing) {
    Log "service already exists status=$($existing.Status)"
} else {
    Log "installing $conf"
    & $wireguard /installtunnelservice $conf
    Log "installtunnelservice exit=$LASTEXITCODE"
    if ($LASTEXITCODE -ne 0) { throw "installtunnelservice $LASTEXITCODE" }
    Start-Sleep -Seconds 3
}
$svc2 = Get-Service -Name $svc -ErrorAction SilentlyContinue
if ($svc2 -and $svc2.Status -ne 'Running') {
    Start-Service -Name $svc
    Start-Sleep -Seconds 2
}
$svc3 = Get-Service -Name $svc -ErrorAction SilentlyContinue
Log "service=$($svc3.Status)"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -like '10.90.91.*' } |
    ForEach-Object { Log ("ip {0} {1}/{2}" -f $_.InterfaceAlias, $_.IPAddress, $_.PrefixLength) }
# Do not add 10.90.90 routes. Do not touch hub.
Log 'done'
