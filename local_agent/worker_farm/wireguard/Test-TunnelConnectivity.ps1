<#
Pings every configured WireGuard peer and shows live interface state.
Run on the workstation after at least one peer has been added and the
secondary machine's WireGuard service is up.

Reads AllowedIPs /32 entries from hub.conf to find peer tunnel IPs.
Does not require Administrator rights.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here    = Split-Path -Parent $PSCommandPath
$wg      = 'C:\Program Files\WireGuard\wg.exe'
$hubConf = Join-Path $here 'hub.conf'

if (-not (Test-Path -LiteralPath $hubConf)) {
    throw "hub.conf not found. Run Generate-HubKeypair.ps1 first."
}

# Extract peer IPs from AllowedIPs = <ip>/32 lines
$peerIps = (Get-Content -LiteralPath $hubConf) |
    ForEach-Object {
        if ($_ -match 'AllowedIPs\s*=\s*([\d.]+)/32') { $matches[1] }
    } |
    Where-Object { $_ }

if (-not $peerIps) {
    Write-Host "No /32 peer entries found in hub.conf." -ForegroundColor Yellow
    Write-Host "Add secondary machines with Add-WireGuardPeer.ps1 first, then re-run." -ForegroundColor Yellow
    return
}

if (Test-Path -LiteralPath $wg) {
    Write-Host "=== wg show hub ===" -ForegroundColor Cyan
    & $wg show hub 2>&1
    Write-Host ""
}

Write-Host "=== Ping test (1 packet each) ===" -ForegroundColor Cyan
$results = @()
foreach ($ip in $peerIps) {
    $ok     = Test-Connection -ComputerName $ip -Count 1 -Quiet -TimeoutSeconds 3 2>$null
    $label  = if ($ok) { 'UP' } else { 'NO REPLY' }
    $color  = if ($ok) { 'Green' } else { 'Red' }
    Write-Host ("  {0,-15} {1}" -f $ip, $label) -ForegroundColor $color
    $results += [PSCustomObject]@{ IP = $ip; Up = $ok }
}

$upCount = ($results | Where-Object { $_.Up }).Count
Write-Host ""
Write-Host "$upCount / $($results.Count) peer(s) reachable." -ForegroundColor $(if ($upCount -eq $results.Count) { 'Green' } else { 'Yellow' })

if ($upCount -lt $results.Count) {
    Write-Host ""
    Write-Host "Troubleshooting for unreachable peers:" -ForegroundColor Yellow
    Write-Host "  1. Confirm hub service is running:  Get-Service 'WireGuardTunnel`$hub'"
    Write-Host "  2. Confirm peer ran Generate-NodeConf.ps1 and installed its WireGuard service"
    Write-Host "  3. Confirm you ran Add-WireGuardPeer.ps1 with that peer's exact public key"
    Write-Host "  4. Confirm the Endpoint LAN IP in node.conf matches the workstation's actual LAN IP"
    Write-Host "  5. Check: wg show hub -- 'latest handshake' should appear when both sides are live"
    Write-Host "  6. Check Windows Firewall -- UDP 51820 inbound must be allowed on the workstation"
}
