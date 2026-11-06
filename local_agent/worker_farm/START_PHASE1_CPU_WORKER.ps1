<#
Launches the intentionally CPU-only Phase 1 worker. It never starts ComfyUI,
loads Ollama, or reserves the RTX GPU.
#>
[CmdletBinding()]
param(
    [int]$Concurrency = 1
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$envFile = Join-Path $here '.env'
$python = Join-Path $here '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envFile)) {
    throw 'Missing local_agent/worker_farm/.env. Configure it before launching a worker.'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing the isolated worker environment. Install local_agent/worker_farm/requirements.txt first.'
}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
if ($env:FARM_ENCRYPTION_KEY_B64 -match '^replace-with-' -or $env:FARM_BROKER_URL -match '^.*replace-with-') {
    throw '.env still contains example placeholders.'
}
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:OLLAMA_HOST = '127.0.0.1:11435'
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $here))
Write-Host 'Starting CPU-only Phase 1 worker on queue: distill' -ForegroundColor Cyan
Write-Host 'This worker does not load a GPU model or start ComfyUI.' -ForegroundColor DarkGray
& $python -m local_agent.worker_farm.worker --queues distill --concurrency ([Math]::Max(1, $Concurrency))
