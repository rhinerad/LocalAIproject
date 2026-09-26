<#
Runs the Phase 1 readiness report with its isolated Python environment. This is
read-only: it does not start Docker, Redis, Celery, a model, or ComfyUI.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $PSCommandPath
$python = Join-Path $here '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing the isolated worker environment. Install local_agent/worker_farm/requirements.txt first.'
}
Set-Location -LiteralPath (Split-Path -Parent (Split-Path -Parent $here))
Write-Host 'Running the read-only Phase 1 readiness report...' -ForegroundColor Cyan
& $python -m local_agent.worker_farm.doctor
exit $LASTEXITCODE
