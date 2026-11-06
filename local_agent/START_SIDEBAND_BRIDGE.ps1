$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    throw 'Do not paste or open this file inside PowerShell. Double-click START_SIDEBAND_BRIDGE.cmd instead.'
}
$AgentUrl = 'http://127.0.0.1:8760/api/status'
$Launcher = Join-Path $PSScriptRoot 'START_LOCAL_AGENT_GUI.ps1'
$Bridge = Join-Path $PSScriptRoot 'lxmf_agent.py'
$RnsConfig = Join-Path $PSScriptRoot 'rns_wifi'
$FirewallSetup = Join-Path $PSScriptRoot 'ENABLE_SIDEBAND_WIFI_FIREWALL.ps1'
$FirewallRule = 'Equal Shares Sideband LXMF WiFi'
$TcpFirewallRule = 'Equal Shares Sideband LXMF Direct LAN'

function Test-AgentReady {
    try {
        $response = Invoke-WebRequest $AgentUrl -TimeoutSec 3 -UseBasicParsing
        return $response.StatusCode -eq 200
    }
    catch { return $false }
}

if (-not (Test-AgentReady)) {
    Write-Host 'Starting the localhost agent and Ollama tiers...' -ForegroundColor Cyan
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Launcher
    )
    # First launch can spend over a minute starting two Ollama tiers, rebuilding
    # the local retrieval index, and recovering a stale watcher.  The bridge
    # must not mislabel that normal one-time work as an agent failure.
    for ($i = 0; $i -lt 150 -and -not (Test-AgentReady); $i++) {
        Start-Sleep -Seconds 1
    }
    if (-not (Test-AgentReady)) {
        throw 'The localhost agent did not become ready after 150 seconds. Run START_LOCAL_AGENT_GUI.ps1 directly; its visible window will show the startup error.'
    }
}

$firewallRuleObject = Get-NetFirewallRule -DisplayName $FirewallRule -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }
$firewallPorts = if ($firewallRuleObject) {
    @($firewallRuleObject | Get-NetFirewallPortFilter | ForEach-Object {
        @($_.LocalPort) -split ',' | ForEach-Object { "$($_)".Trim() }
    })
} else { @() }
$firewallAddresses = if ($firewallRuleObject) {
    @($firewallRuleObject | Get-NetFirewallAddressFilter | ForEach-Object {
        @($_.RemoteAddress) -split ',' | ForEach-Object { "$($_)".Trim() }
    })
} else { @() }
$firewallHasPublicProfile = @($firewallRuleObject | Where-Object {
    (([int]$_.Profile -band 4) -ne 0)
}).Count -gt 0
$firewallReady = $firewallRuleObject -and
    ('29716' -in $firewallPorts) -and
    ('29717' -in $firewallPorts) -and
    ('42671' -in $firewallPorts) -and
    ('LocalSubnet' -in $firewallAddresses) -and
    ('fe80::/10' -in $firewallAddresses) -and
    $firewallHasPublicProfile
$tcpRuleObject = Get-NetFirewallRule -DisplayName $TcpFirewallRule -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }
$tcpPorts = if ($tcpRuleObject) { @($tcpRuleObject | Get-NetFirewallPortFilter | ForEach-Object { @($_.LocalPort) }) } else { @() }
$tcpHasPublicProfile = @($tcpRuleObject | Where-Object { (([int]$_.Profile -band 4) -ne 0) }).Count -gt 0
$tcpProgram = @($tcpRuleObject | Get-NetFirewallApplicationFilter | ForEach-Object { $_.Program })
$tcpHasPortableAppScope = 'Any' -in $tcpProgram
$broadTcpReady = $tcpRuleObject -and ('4242' -in $tcpPorts) -and $tcpHasPublicProfile -and $tcpHasPortableAppScope

# A deliberately created phone-only rule is also sufficient for the nearby
# Sideband fallback. Do not repeatedly request elevation to widen it into a
# whole-subnet rule once a paired phone can already reach TCP/4242.
$phoneRuleObject = Get-NetFirewallRule -DisplayName 'Equal Shares Sideband LXMF Phone *' -ErrorAction SilentlyContinue |
    Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }
$phonePorts = if ($phoneRuleObject) {
    @($phoneRuleObject | Get-NetFirewallPortFilter | ForEach-Object { @($_.LocalPort) })
} else { @() }
$phoneTcpReady = $phoneRuleObject -and ('4242' -in $phonePorts)

$firewallReady = $firewallReady -and ($broadTcpReady -or $phoneTcpReady)
if (-not $firewallReady) {
    Write-Host 'Windows needs one administrator confirmation to enable private-LAN LXMF traffic.' -ForegroundColor Yellow
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    try {
        # UAC can fail with 0xc0000142 when it inherits this long project working
        # directory. Elevate from Windows' own directory; the script paths remain
        # absolute in the argument list.
        $elevated = Start-Process -FilePath 'powershell.exe' -Verb RunAs -Wait -PassThru -WorkingDirectory $env:WINDIR -ArgumentList @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $FirewallSetup, '-PythonPath', $pythonPath
        )
        if ($elevated.ExitCode -ne 0) { throw 'administrator setup returned a non-zero exit code' }
    } catch {
        # The USB RNode is an independent Reticulum transport; do not prevent
        # nearby LoRa messaging just because an optional LAN firewall prompt is
        # unavailable. TCP/AutoInterface remains unavailable until the rule is
        # installed, but localhost HTTP is never opened either way.
        $rnsConfigFile = Join-Path $RnsConfig 'config'
        $hasRNode = (Test-Path $rnsConfigFile -PathType Leaf) -and ((Get-Content $rnsConfigFile -Raw) -match 'type\s*=\s*RNodeInterface')
        if (-not $hasRNode) { throw 'The Sideband LAN firewall rule was not installed or updated.' }
        Write-Warning 'LAN firewall setup was unavailable. Continuing with the configured USB RNode LoRa transport only; Wi-Fi/TCP fallback may not accept inbound connections.'
    }
}

python $Bridge --check
Write-Host "`nStarting the opt-in Sideband bridge over Wi-Fi..." -ForegroundColor Green
Write-Host 'HTTP remains private on 127.0.0.1; only LXMF uses Wi-Fi.' -ForegroundColor DarkGray
python $Bridge --rns-config $RnsConfig
