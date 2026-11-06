<#
Generates the workstation's WireGuard keypair and writes the initial hub.conf.
Run once, after WireGuard is installed. If hub.conf already exists this script
aborts rather than overwriting -- the private key cannot be recovered after
regeneration without reconfiguring every peer.

Private key: wireguard\hub-private.key  (gitignored; keep safe)
Public key:  wireguard\hub-public.key   (share this with secondary machines)
Config:      wireguard\hub.conf         (gitignored; contains private key)

[Peer] blocks are added later -- one per secondary machine -- with
Add-WireGuardPeer.ps1. See docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$wg   = 'C:\Program Files\WireGuard\wg.exe'

if (-not (Test-Path -LiteralPath $wg)) {
    throw "WireGuard not found at '$wg'. Install from https://www.wireguard.com/install/ first."
}

$hubConf  = Join-Path $here 'hub.conf'
$privFile = Join-Path $here 'hub-private.key'
$pubFile  = Join-Path $here 'hub-public.key'

if (Test-Path -LiteralPath $hubConf) {
    throw ("hub.conf already exists. Delete it and hub-private.key manually only if you truly " +
           "need to regenerate -- doing so invalidates every existing peer config.")
}

Write-Host "Generating WireGuard keypair for hub (workstation 10.90.90.1)..." -ForegroundColor Cyan

$privateKey = & $wg genkey
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($privateKey)) {
    throw "wg genkey failed."
}
$publicKey = ($privateKey | & $wg pubkey)
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($publicKey)) {
    throw "wg pubkey failed."
}

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($privFile, $privateKey.Trim() + [Environment]::NewLine, $utf8NoBom)
[System.IO.File]::WriteAllText($pubFile,  $publicKey.Trim()  + [Environment]::NewLine, $utf8NoBom)

# hub.conf skeleton -- peer blocks appended by Add-WireGuardPeer.ps1
$conf = @"
# WireGuard hub config -- workstation (10.90.90.1)
# Generated $(Get-Date -Format o)
# Do NOT commit this file -- it contains the hub private key.
# Add secondary machines with Add-WireGuardPeer.ps1.
[Interface]
Address    = 10.90.90.1/28
ListenPort = 51820
PrivateKey = $($privateKey.Trim())

"@
[System.IO.File]::WriteAllText($hubConf, $conf, $utf8NoBom)

Write-Host ""
Write-Host "Done. Files written:" -ForegroundColor Green
Write-Host "  $hubConf   <- WireGuard service config; contains private key; gitignored" -ForegroundColor Yellow
Write-Host "  $privFile  <- private key backup; gitignored; keep safe" -ForegroundColor Yellow
Write-Host "  $pubFile   <- public key to share with each secondary machine" -ForegroundColor Green
Write-Host ""
Write-Host "Hub public key (give this to secondary machines):" -ForegroundColor Green
Write-Host "  $publicKey" -ForegroundColor White
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Install-WireGuardHubService.ps1   (registers hub.conf as a Windows service)"
Write-Host "  2. For each secondary machine: Add-WireGuardPeer.ps1 -NodeName <name> -NodePublicKey <key> -NodeTunnelIp 10.90.90.x"
