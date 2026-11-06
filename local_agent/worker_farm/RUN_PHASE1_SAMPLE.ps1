<#
Queues the benign synthetic distillation fixture. A CPU worker must already be
running. This command cannot stage a real operator export because it passes
only --sample.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$envFile = Join-Path $here '.env'
$python = Join-Path $here '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $envFile) -or -not (Test-Path -LiteralPath $python)) {
    throw 'Missing .env or the isolated worker environment.'
}
Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { Set-Item -Path "Env:$($matches[1])" -Value $matches[2] }
}
$env:CUDA_VISIBLE_DEVICES = '-1'
$env:OLLAMA_HOST = '127.0.0.1:11435'
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $here))
Write-Host 'Queueing the benign synthetic review-only sample...' -ForegroundColor Cyan
& $python -m local_agent.worker_farm.submit_distillation --sample
