param(
    [Parameter(Mandatory = $true)]
    [string]$PythonPath
)

$ErrorActionPreference = 'Stop'
$RuleName = 'Equal Shares Sideband LXMF WiFi'
$TcpRuleName = 'Equal Shares Sideband LXMF Direct LAN'

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable not found: $PythonPath"
}

$existing = Get-NetFirewallRule -DisplayName $RuleName -ErrorAction SilentlyContinue
if ($existing) {
    $existing | Set-NetFirewallRule `
        -Description 'Allow only Reticulum AutoInterface discovery/data for Equal Shares Sideband from the local subnet.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Private,Public `
        -ErrorAction Stop
    $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter `
        -Protocol UDP `
        -LocalPort 29716,29717,42671 `
        -RemotePort Any `
        -ErrorAction Stop
    $existing | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter `
        -RemoteAddress @('LocalSubnet', 'fe80::/10') `
        -ErrorAction Stop
} else {
    New-NetFirewallRule `
        -DisplayName $RuleName `
        -Description 'Allow only Reticulum AutoInterface discovery/data for Equal Shares Sideband from the local subnet.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Private,Public `
        -Program $PythonPath `
        -Protocol UDP `
        -LocalPort 29716,29717,42671 `
        -RemoteAddress @('LocalSubnet', 'fe80::/10') `
        -ErrorAction Stop | Out-Null
}

$existingTcp = Get-NetFirewallRule -DisplayName $TcpRuleName -ErrorAction SilentlyContinue
if ($existingTcp) {
    $existingTcp | Set-NetFirewallRule `
        -Description 'Allow only Reticulum TCP fallback for Equal Shares Sideband from the local subnet.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Private,Public `
        -ErrorAction Stop
    $existingTcp | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter `
        -Protocol TCP `
        -LocalPort 4242 `
        -RemotePort Any `
        -ErrorAction Stop
    $existingTcp | Get-NetFirewallAddressFilter | Set-NetFirewallAddressFilter `
        -RemoteAddress LocalSubnet `
        -ErrorAction Stop
    # The bridge may be launched by a different local Windows account. Keep the
    # transport boundary at TCP/4242 + LocalSubnet, rather than silently tying
    # it to a Python executable path owned by a different account.
    $existingTcp | Get-NetFirewallApplicationFilter | Set-NetFirewallApplicationFilter `
        -Program Any `
        -Package Any `
        -ErrorAction Stop
} else {
    New-NetFirewallRule `
        -DisplayName $TcpRuleName `
        -Description 'Allow only Reticulum TCP fallback for Equal Shares Sideband from the local subnet.' `
        -Direction Inbound `
        -Action Allow `
        -Enabled True `
        -Profile Private,Public `
        -Protocol TCP `
        -LocalPort 4242 `
        -RemoteAddress LocalSubnet `
        -ErrorAction Stop | Out-Null
}

Write-Host 'Sideband LAN access is enabled for Reticulum UDP discovery/data and TCP fallback port 4242, limited to the local subnet.' -ForegroundColor Green
