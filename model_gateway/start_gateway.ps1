# Model gateway preflight (Windows). There is no separate gateway process:
# the hybrid router lives inside local_agent (Option B). This script arms the
# cloud tier for the current PowerShell session, verifies both Ollama tiers,
# and prints the Claude Code environment block for local-model CLI use.
#
#   .\model_gateway\start_gateway.ps1              # report only
#   .\model_gateway\start_gateway.ps1 -Enable      # set MODEL_GATEWAY_CLOUD=1 for this shell
#   .\model_gateway\start_gateway.ps1 -CloudCheck  # one tiny cloud round trip (costs tokens)
#   .\model_gateway\start_gateway.ps1 -Strict      # non-zero exit if the cloud tier is armed but broken
#
# Put ANTHROPIC_API_KEY in model_gateway\.env (see env.example); it is read
# by load_config() without overriding variables already set in this shell.
param(
    [switch]$Enable,
    [switch]$CloudCheck,
    [switch]$Strict,
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

if ($Enable) {
    $env:MODEL_GATEWAY_CLOUD = "1"
    Write-Host "MODEL_GATEWAY_CLOUD=1 for this shell. Start the agent from this same shell:" -ForegroundColor Cyan
    Write-Host "  .\local_agent\START_LOCAL_AGENT_GUI.ps1" -ForegroundColor Cyan
}

$args = @()
if ($CloudCheck) { $args += "--cloud-check" }
if ($Strict)     { $args += "--strict" }
& $Python "model_gateway\preflight.py" @args
exit $LASTEXITCODE
