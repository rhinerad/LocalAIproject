# New isolated Pixel overlay 10.90.91.0/30 (G1).
# Does NOT edit worker_farm/wireguard/hub.conf or any Mac config.
# Writes keys under this package's runtime/ directory (gitignored).
# Does not install a WireGuard service unless -Install is passed.

param(
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$outDir = Join-Path $here "runtime\wireguard"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

$wg = "C:\Program Files\WireGuard\wg.exe"
if (-not (Test-Path $wg)) {
    throw "wg.exe not found; install WireGuard for Windows first"
}

$hubPriv = & $wg genkey
$hubPub = $hubPriv | & $wg pubkey
$phonePriv = & $wg genkey
$phonePub = $phonePriv | & $wg pubkey

# Workstation side of the /30. AllowedIPs is the phone /32 only.
$hubConf = @"
[Interface]
Address = 10.90.91.1/30
ListenPort = 51821
PrivateKey = $hubPriv

[Peer]
PublicKey = $phonePub
AllowedIPs = 10.90.91.2/32
"@

# Pixel side. AllowedIPs is the workstation /32 only. No 10.90.90.0/28.
$phoneConf = @"
[Interface]
Address = 10.90.91.2/30
PrivateKey = $phonePriv

[Peer]
PublicKey = $hubPub
Endpoint = 10.90.91.1:51821
AllowedIPs = 10.90.91.1/32
PersistentKeepalive = 25
"@

Set-Content -Path (Join-Path $outDir "edge-phone.conf") -Value $hubConf -Encoding ascii
Set-Content -Path (Join-Path $outDir "pixel.conf") -Value $phoneConf -Encoding ascii
Set-Content -Path (Join-Path $outDir "README.txt") -Value @"
G1 isolated overlay. USB/ADB copy pixel.conf to the phone (G5).
Do not merge this peer into the farm hub (10.90.90.0/28).
Do not set AllowedIPs to 10.90.90.0/28.
Install the workstation tunnel only with this script's -Install.
"@ -Encoding ascii

Write-Output "wrote $outDir\edge-phone.conf and pixel.conf"

if ($Install) {
    $wgSvc = "C:\Program Files\WireGuard\wireguard.exe"
    & $wgSvc /installtunnelservice (Join-Path $outDir "edge-phone.conf")
}
