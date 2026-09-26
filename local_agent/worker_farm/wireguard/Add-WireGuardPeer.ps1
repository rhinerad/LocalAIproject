<#
Adds one secondary machine as a WireGuard peer on the hub.

Run once per secondary machine AFTER:
  - Generate-HubKeypair.ps1 has created hub.conf
  - The secondary machine has run Generate-NodeConf.ps1 and sent you its public key

Parameters
  -NodeName      Short label for the [Peer] comment, e.g. "workshop_pc"
  -NodePublicKey The secondary machine's WireGuard public key (base64, 44 chars)
  -NodeTunnelIp  The /32 tunnel IP to assign: 10.90.90.2 through 10.90.90.14

Appends a [Peer] block to hub.conf. If the WireGuard 'hub' interface is
already running, also adds the peer live without a service restart.

After adding the peer, tell the secondary machine operator:
  - Their assigned tunnel IP (NodeTunnelIp) -- they already have it from Generate-NodeConf.ps1
  - The hub's LAN IP (find with ipconfig -- NOT the tunnel IP 10.90.90.1)
  - The hub's public key (wireguard\hub-public.key)
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$NodeName,
    [Parameter(Mandatory)][string]$NodePublicKey,
    [Parameter(Mandatory)][string]$NodeTunnelIp
)

$ErrorActionPreference = 'Stop'
$here    = Split-Path -Parent $PSCommandPath
$wg      = 'C:\Program Files\WireGuard\wg.exe'
$hubConf = Join-Path $here 'hub.conf'

if (-not (Test-Path -LiteralPath $hubConf)) {
    throw "hub.conf not found. Run Generate-HubKeypair.ps1 first."
}
if ($NodeName -notmatch '^[a-zA-Z0-9_-]+$') {
    throw "NodeName '$NodeName' must contain only letters, digits, underscores, or hyphens."
}
if ($NodePublicKey -notmatch '^[A-Za-z0-9+/]{43}=$') {
    throw "NodePublicKey does not look like a WireGuard public key (expected 43 base64 chars + '=')."
}

try {
    $ip    = [System.Net.IPAddress]::Parse($NodeTunnelIp)
    $parts = $ip.ToString().Split('.')
    if ($parts[0] -ne '10' -or $parts[1] -ne '90' -or $parts[2] -ne '90') {
        throw "must be in 10.90.90.x"
    }
    $last = [int]$parts[3]
    if ($last -lt 2 -or $last -gt 14) {
        throw "last octet must be 2-14 (workstation is .1; /28 ends at .14)"
    }
} catch {
    throw "NodeTunnelIp '$NodeTunnelIp' is not valid for this subnet: $_"
}

$existing = Get-Content -LiteralPath $hubConf -Raw
if ($existing -match [regex]::Escape($NodePublicKey)) {
    throw "Public key is already present in hub.conf -- each machine needs a unique keypair."
}
if ($existing -match [regex]::Escape("$NodeTunnelIp/32")) {
    throw "Tunnel IP $NodeTunnelIp/32 is already in hub.conf -- each machine needs a unique IP."
}

$block = @"

# Peer: $NodeName -- added $(Get-Date -Format o)
[Peer]
PublicKey  = $NodePublicKey
AllowedIPs = $NodeTunnelIp/32

"@
Add-Content -LiteralPath $hubConf -Value $block -Encoding UTF8
Write-Host "Appended [Peer] for '$NodeName' ($NodeTunnelIp) to hub.conf." -ForegroundColor Green

# Update the live interface without a restart if it is already running
if (Test-Path -LiteralPath $wg) {
    $liveCheck = & $wg show hub 2>&1
    if ($LASTEXITCODE -eq 0 -and "$liveCheck" -match 'interface') {
        Write-Host "WireGuard interface 'hub' is running -- adding peer live..." -ForegroundColor Cyan
        & $wg set hub peer $NodePublicKey allowed-ips "$NodeTunnelIp/32"
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Peer added to live interface." -ForegroundColor Green
        } else {
            Write-Host "Live 'wg set' failed. hub.conf is updated -- restart the service to apply." -ForegroundColor Yellow
        }
    } else {
        Write-Host "WireGuard service not yet running -- hub.conf is updated; will apply on service start." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Remind '$NodeName' operator to give you their public key (node-public.key) if not done already."
Write-Host "Run Test-TunnelConnectivity.ps1 after the secondary machine's WireGuard service is up."
