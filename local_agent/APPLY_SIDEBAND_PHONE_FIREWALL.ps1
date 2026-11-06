# One-time recovery rule for the currently paired phone on the home LAN.
# This intentionally exposes only Reticulum TCP 4242 to this exact address.
$ErrorActionPreference = 'Stop'
$PhoneIp = '192.168.50.80'
$RuleName = 'Equal Shares Sideband LXMF Phone 192.168.50.80'

[void][System.Net.IPAddress]::Parse($PhoneIp)
$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Set-NetFirewallRule `
        -Description 'Allow only the paired Sideband phone to reach local Reticulum TCP 4242.' `
        -Direction Inbound -Action Allow -Enabled True -Profile Private,Public `
        -ErrorAction Stop
    $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter `
        -Protocol TCP -LocalPort 4242 -RemotePort Any -ErrorAction Stop
    $existing | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter `
        -RemoteAddress $PhoneIp -ErrorAction Stop
} else {
    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Description 'Allow only the paired Sideband phone to reach local Reticulum TCP 4242.' `
        -Direction Inbound -Action Allow -Enabled True -Profile Private,Public `
        -Protocol TCP -LocalPort 4242 -RemoteAddress $PhoneIp `
        -ErrorAction Stop | Out-Null
}

Write-Host "Applied phone-only Sideband rule: $PhoneIp -> TCP 4242." -ForegroundColor Green
