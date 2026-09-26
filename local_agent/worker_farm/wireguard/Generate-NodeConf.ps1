<#
Generates the WireGuard config for one secondary (spoke) node.
Run this ON THE SECONDARY MACHINE, not on the workstation.

Works on Windows (PowerShell 5.1+) and PowerShell Core on Linux/macOS.

Writes three files next to this script:
  node-private.key  -- private key for this machine (gitignored; keep safe)
  node-public.key   -- public key to give to the hub operator
  node.conf         -- WireGuard tunnel config to install as a service/interface

Required parameters (get these from the hub operator):
  -HubPublicKey     The workstation's WireGuard public key (from hub-public.key)
  -ThisNodeTunnelIp The /32 tunnel IP assigned to this machine, e.g. 10.90.90.2
  -HubLanIp         The workstation's LAN (Wi-Fi/Ethernet) IP, NOT 10.90.90.1
                    Find it with: ipconfig (Windows) or ip addr (Linux)

After running, send node-public.key back to the hub operator so they can run
Add-WireGuardPeer.ps1. Install node.conf:
  Windows: wireguard /installtunnelservice <path-to-node.conf>  (as Administrator)
  Linux:   sudo cp node.conf /etc/wireguard/node.conf && sudo wg-quick up node
  macOS:   sudo wg-quick up <path-to-node.conf>

See docs/WORKER_FARM_MULTI_NODE_LAN_PLAN_2026-09-01.md
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$HubPublicKey,
    [Parameter(Mandatory)][string]$ThisNodeTunnelIp,
    [Parameter(Mandatory)][string]$HubLanIp
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath

# Locate wg -- Windows default path, fallback to PATH
$wg = 'C:\Program Files\WireGuard\wg.exe'
if (-not (Test-Path -LiteralPath $wg -ErrorAction SilentlyContinue)) {
    $wgCmd = Get-Command wg -ErrorAction SilentlyContinue
    if (-not $wgCmd) {
        throw "WireGuard 'wg' not found. Install WireGuard (https://www.wireguard.com/install/) first."
    }
    $wg = $wgCmd.Source
}

$confFile = Join-Path $here 'node.conf'
$privFile = Join-Path $here 'node-private.key'
$pubFile  = Join-Path $here 'node-public.key'

if (Test-Path -LiteralPath $confFile) {
    throw "node.conf already exists. Delete it and node-private.key manually to regenerate."
}
if ($HubPublicKey -notmatch '^[A-Za-z0-9+/]{43}=$') {
    throw "HubPublicKey does not look like a WireGuard public key (43 base64 chars + '=')."
}
try {
    $ip    = [System.Net.IPAddress]::Parse($ThisNodeTunnelIp)
    $parts = $ip.ToString().Split('.')
    if ($parts[0] -ne '10' -or $parts[1] -ne '90' -or $parts[2] -ne '90') { throw "" }
    $last = [int]$parts[3]
    if ($last -lt 2 -or $last -gt 14) { throw "" }
} catch {
    throw "ThisNodeTunnelIp '$ThisNodeTunnelIp' is not a valid spoke address (must be 10.90.90.2-14)."
}

Write-Host "Generating WireGuard keypair for this node ($ThisNodeTunnelIp)..." -ForegroundColor Cyan

$privateKey = & $wg genkey
if ($LASTEXITCODE -ne 0) { throw "wg genkey failed." }
$publicKey = ($privateKey | & $wg pubkey)
if ($LASTEXITCODE -ne 0) { throw "wg pubkey failed." }

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[System.IO.File]::WriteAllText($privFile, $privateKey.Trim() + [Environment]::NewLine, $utf8NoBom)
[System.IO.File]::WriteAllText($pubFile,  $publicKey.Trim()  + [Environment]::NewLine, $utf8NoBom)

$conf = @"
# WireGuard node config -- $ThisNodeTunnelIp
# Generated $(Get-Date -Format o)
# Sole peer is the hub (workstation 10.90.90.1).
# Do NOT commit this file -- it contains this node's private key.
[Interface]
Address    = $ThisNodeTunnelIp/28
PrivateKey = $($privateKey.Trim())

# Hub / workstation
[Peer]
PublicKey           = $HubPublicKey
AllowedIPs          = 10.90.90.0/28
Endpoint            = ${HubLanIp}:51820
PersistentKeepalive = 25

"@
[System.IO.File]::WriteAllText($confFile, $conf, $utf8NoBom)

Write-Host ""
Write-Host "Done. Files written:" -ForegroundColor Green
Write-Host "  $confFile   <- install as a WireGuard service/interface" -ForegroundColor Yellow
Write-Host "  $privFile   <- private key; keep safe; gitignored" -ForegroundColor Yellow
Write-Host "  $pubFile    <- public key to give to the hub operator" -ForegroundColor Green
Write-Host ""
Write-Host "This node's public key (give to hub operator):" -ForegroundColor Green
Write-Host "  $publicKey" -ForegroundColor White
Write-Host ""
Write-Host "Install the tunnel:" -ForegroundColor Cyan
Write-Host "  Windows (Admin): wireguard /installtunnelservice `"$confFile`""
Write-Host "  Linux:           sudo cp node.conf /etc/wireguard/node.conf && sudo wg-quick up node"
Write-Host "  macOS:           sudo wg-quick up `"$confFile`""
Write-Host ""
Write-Host "After the hub operator runs Add-WireGuardPeer.ps1, verify: ping 10.90.90.1"
