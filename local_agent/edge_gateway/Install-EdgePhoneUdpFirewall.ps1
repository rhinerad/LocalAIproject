# Elevated: inbound UDP 51821 for the isolated edge-phone overlay only.
# Does NOT edit hub.conf, WireGuardTunnel$hub, or UDP 51820.
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
$name = 'WireGuard Edge-Phone UDP 51821'
$existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
if ($existing) {
    Log "rule already exists Enabled=$($existing.Enabled) Action=$($existing.Action)"
} else {
    New-NetFirewallRule -DisplayName $name -Direction Inbound -Protocol UDP -LocalPort 51821 -Action Allow -Profile Any | Out-Null
    Log "created $name inbound UDP 51821 Allow"
}
Get-NetUDPEndpoint -LocalPort 51821 -ErrorAction SilentlyContinue |
    ForEach-Object { Log ("listen {0}:{1} pid={2}" -f $_.LocalAddress, $_.LocalPort, $_.OwningProcess) }
Log 'done'
