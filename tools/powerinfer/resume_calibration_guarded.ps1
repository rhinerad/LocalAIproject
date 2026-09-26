[CmdletBinding()]
param(
    [string]$ModelId = 'relu-llama-7b',
    [string]$Vault = 'A:\PowerInferModels',
    [string]$BuildId = 'relu-llama-7b-source-20260829',
    [string]$PredictorWorkspace = 'A:\Users\rhine\Documents\Codex\PowerInferStaging\relu-llama-7b-source-20260829',
    [int]$StartLayer = 20,
    [int]$EndLayer = 31,
    [int]$WaitForCheckpointLayer = 19,
    [int]$TrainSamples = 25000,
    [int]$PredictorRank = 256,
    [int]$TrainBatchSize = 256,
    [int]$TrainEpochs = 2,
    [int]$StartMaxC = 70,
    [int]$EmergencyC = 82
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# This is deliberately a narrow continuation helper, not a general GPU launcher.
# It trains only absent PowerInfer predictor checkpoints, one layer per child
# process, and stops the child immediately at the documented emergency ceiling.
$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Pipeline = Join-Path $ScriptRoot 'run_pipeline.ps1'
$RawDir = Join-Path $PredictorWorkspace 'predictor_raw'
$NvidiaSmi = Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'
$Pwsh = (Get-Command 'pwsh.exe' -ErrorAction Stop).Source

function Get-GpuTemperatureC {
    if (-not (Test-Path -LiteralPath $NvidiaSmi -PathType Leaf)) {
        throw "nvidia-smi was not found at $NvidiaSmi"
    }
    $raw = & $NvidiaSmi '--query-gpu=temperature.gpu' '--format=csv,noheader,nounits' 2>$null
    $first = @($raw | Where-Object { $_.ToString().Trim() })[0]
    $value = 0
    if (-not [int]::TryParse($first.ToString().Trim(), [ref]$value)) {
        throw "Unable to read GPU temperature from nvidia-smi: $first"
    }
    return $value
}

function Wait-ForCoolGpu {
    while ($true) {
        $temp = Get-GpuTemperatureC
        if ($temp -lt $EmergencyC) { break }
        Write-Warning "Thermal hold: GPU is $temp C; waiting for it to fall below $EmergencyC C."
        Start-Sleep -Seconds 15
    }
    while ($temp -gt $StartMaxC) {
        Write-Host "Cooldown hold: GPU is $temp C; waiting for <= $StartMaxC C before the next layer."
        Start-Sleep -Seconds 15
        $temp = Get-GpuTemperatureC
    }
    Write-Host "Thermal preflight passed at $temp C."
}

function Wait-ForCheckpoint([int]$Layer) {
    $path = Join-Path $RawDir ("model_{0}.pt" -f $Layer)
    $deadline = (Get-Date).AddHours(2)
    while (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        if ((Get-Date) -gt $deadline) {
            throw "Timed out waiting for the prior checkpoint: $path"
        }
        Write-Host "Waiting for active batch to finish layer $Layer..."
        Start-Sleep -Seconds 30
    }
}

if ($StartLayer -lt 0 -or $EndLayer -lt $StartLayer -or $EndLayer -gt 31) {
    throw 'Layers must be an inclusive range within 0..31.'
}

if ($WaitForCheckpointLayer -ge 0) { Wait-ForCheckpoint $WaitForCheckpointLayer }

foreach ($layer in $StartLayer..$EndLayer) {
    $checkpoint = Join-Path $RawDir ("model_{0}.pt" -f $layer)
    if (Test-Path -LiteralPath $checkpoint -PathType Leaf) {
        Write-Host "Checkpoint already exists for layer $layer; preserving it and skipping."
        continue
    }

    Wait-ForCoolGpu
    $argList = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Pipeline,
        '-ModelId', $ModelId, '-Stage', 'train', '-Execute', '-Vault', $Vault,
        '-BuildId', $BuildId, '-PredictorWorkspace', $PredictorWorkspace,
        '-LayerStart', $layer, '-LayerCount', '1', '-TrainSamples', "$TrainSamples",
        '-PredictorRank', "$PredictorRank", '-TrainBatchSize', "$TrainBatchSize",
        '-TrainEpochs', "$TrainEpochs"
    )
    Write-Host "Starting guarded predictor calibration for layer $layer."
    # The runner uses PowerShell 7 argument splatting for its Python command
    # invocation. Windows PowerShell 5.1 collapses this argument list and makes
    # Python treat the script and all flags as one filename.
    $child = Start-Process -FilePath $Pwsh -ArgumentList $argList -PassThru -NoNewWindow
    while (-not $child.HasExited) {
        Start-Sleep -Seconds 15
        $temp = Get-GpuTemperatureC
        if ($temp -ge $EmergencyC) {
            Write-Error "THERMAL STOP: GPU reached $temp C while layer $layer was running."
            Stop-Process -Id $child.Id -Force -ErrorAction SilentlyContinue
            throw "Stopped layer $layer at the $EmergencyC C emergency ceiling."
        }
        $child.Refresh()
    }
    $child.WaitForExit()
    $exitCode = $child.ExitCode
    if ($exitCode -ne 0) {
        throw "Layer $layer failed with exit code $exitCode."
    }
    if (-not (Test-Path -LiteralPath $checkpoint -PathType Leaf)) {
        throw "Layer $layer exited successfully but did not create $checkpoint."
    }
    Write-Host "Layer $layer completed."
}

Write-Host "Guarded calibration continuation completed through layer $EndLayer."
