<# Displays metadata-only job state; no secrets or raw source content are printed. #>
[CmdletBinding()]
param([string]$JobId, [int]$Limit = 20)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$python = Join-Path $here '.venv\Scripts\python.exe'
$envFile = Join-Path $here '.env'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing .env or isolated worker environment.'
}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $here))
if ($JobId) { & $python -m local_agent.worker_farm.status --job $JobId }
else { & $python -m local_agent.worker_farm.status --limit ([Math]::Max(1, $Limit)) }
