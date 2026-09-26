[CmdletBinding()]
param(
    # The approved-pair gate is deliberately external to the repository.  This
    # path must contain >=32 human-reviewed contrastive records; the synthetic
    # eight-row fixture is never accepted here.
    [string]$ApprovedPairsPath = 'A:\PowerInferModels\turbosparse-mistral\approved_pairs.jsonl',
    [string]$RawSource = 'A:\Users\rhine\Documents\Codex\PowerInferStaging\turbosparse-mistral-instruct-source-20260830',
    [string]$Vault = 'A:\PowerInferModels',
    [string]$NotBefore = '02:00',
    [int]$IdlePollSeconds = 60,
    [int]$MaxWaitMinutes = 480,
    [int]$StartMaxC = 70,
    [int]$EmergencyC = 82,
    # Creating the immutable edit and activation profile is safe to automate
    # overnight after every gate passes.  Predictor training is intentionally
    # opt-in because its duration/profile must be selected explicitly.
    [switch]$RunPredictorTraining,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Tools = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Tools '..\..')).Path
$ModelId = 'turbosparse-mistral-instruct'
$Py = Join-Path $Repo 'external\PowerInfer\.venv\Scripts\python.exe'
$Pipeline = Join-Path $Tools 'run_pipeline.ps1'
$NvidiaSmi = Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'
$StatusDir = Join-Path $Vault "$ModelId\overnight_status"

if (-not (Test-Path -LiteralPath $Py -PathType Leaf)) {
    throw "PowerInfer virtual environment is missing: $Py"
}
if (-not (Test-Path -LiteralPath $NvidiaSmi -PathType Leaf)) {
    throw "nvidia-smi is missing: $NvidiaSmi"
}
if ($IdlePollSeconds -lt 15) { throw 'IdlePollSeconds must be at least 15.' }
if ($MaxWaitMinutes -lt 1) { throw 'MaxWaitMinutes must be positive.' }
if ($EmergencyC -gt 82 -or $EmergencyC -le $StartMaxC) {
    throw 'EmergencyC must be <= 82 C and greater than StartMaxC.'
}

function Write-Status([string]$State, [string]$Detail, [hashtable]$Extra = @{}) {
    $record = [ordered]@{
        timestamp = (Get-Date).ToUniversalTime().ToString('o')
        state = $State
        detail = $Detail
        model_id = $ModelId
        approved_pairs = $ApprovedPairsPath
        raw_source = $RawSource
        vault = $Vault
    }
    foreach ($key in $Extra.Keys) { $record[$key] = $Extra[$key] }
    $line = $record | ConvertTo-Json -Compress -Depth 6
    Write-Host $line
    if (-not $WhatIf) {
        New-Item -ItemType Directory -Force -Path $StatusDir | Out-Null
        Add-Content -LiteralPath (Join-Path $StatusDir 'events.jsonl') -Value $line -Encoding utf8
    }
}

function Get-GpuTemperatureC {
    $raw = & $NvidiaSmi '--query-gpu=temperature.gpu' '--format=csv,noheader,nounits' 2>$null
    $value = 0
    $first = @($raw | Where-Object { $_.ToString().Trim() })[0]
    if (-not [int]::TryParse($first.ToString().Trim(), [ref]$value)) {
        throw "Unable to read GPU temperature: $first"
    }
    return $value
}

function Get-GpuIdleReport {
    # router.gpu_busy() combines ComfyUI port/queue ownership, nvidia-smi,
    # PowerInfer, and Ollama /api/ps. It regards unknown telemetry as busy.
    $code = @"
import json, sys
sys.path.insert(0, r'$Repo\\local_agent')
import router
busy, reason, detail = router.gpu_busy()
print(json.dumps({'busy': busy, 'reason': reason, 'detail': detail}, sort_keys=True))
"@
    $raw = & $Py -c $code 2>&1
    if ($LASTEXITCODE -ne 0) {
        return [pscustomobject]@{ busy = $true; reason = "GPU state probe failed: $($raw -join ' ')"; detail = @{} }
    }
    try { return ($raw | Out-String | ConvertFrom-Json) }
    catch { return [pscustomobject]@{ busy = $true; reason = "GPU state probe returned invalid JSON: $raw"; detail = @{} } }
}

function Wait-ForWindowAndIdle {
    $due = [datetime]::Today.Add([timespan]::Parse($NotBefore))
    if ((Get-Date) -lt $due) {
        Write-Status 'waiting_for_time' "not before $($due.ToString('yyyy-MM-dd HH:mm')) local time"
        while ((Get-Date) -lt $due) { Start-Sleep -Seconds ([Math]::Min(60, $IdlePollSeconds)) }
    }
    $deadline = (Get-Date).AddMinutes($MaxWaitMinutes)
    while ($true) {
        if ((Get-Date) -gt $deadline) { throw "Timed out after $MaxWaitMinutes minutes waiting for an idle GPU." }
        $temp = Get-GpuTemperatureC
        $idle = Get-GpuIdleReport
        if (-not $idle.busy -and $temp -le $StartMaxC) {
            Write-Status 'gpu_idle' $idle.reason @{ temperature_c = $temp }
            return
        }
        Write-Status 'waiting_for_gpu' $idle.reason @{ temperature_c = $temp }
        Start-Sleep -Seconds $IdlePollSeconds
    }
}

function Invoke-Checked([string]$Label, [string]$File, [string[]]$Arguments, [switch]$GpuWork) {
    if ($WhatIf) {
        Write-Status 'what_if' "$Label would run" @{ command = @($File) + $Arguments }
        return
    }
    if ($GpuWork) {
        $temp = Get-GpuTemperatureC
        if ($temp -gt $StartMaxC) { throw "$Label refused: GPU is $temp C (must be <= $StartMaxC C)." }
    }
    Write-Status 'starting' $Label
    $child = Start-Process -FilePath $File -ArgumentList $Arguments -PassThru -NoNewWindow
    while (-not $child.HasExited) {
        Start-Sleep -Seconds 15
        if ($GpuWork) {
            $temp = Get-GpuTemperatureC
            if ($temp -ge $EmergencyC) {
                Stop-Process -Id $child.Id -ErrorAction SilentlyContinue
                throw "THERMAL STOP: stopped $Label at $temp C (emergency ceiling $EmergencyC C)."
            }
        }
        $child.Refresh()
    }
    $child.WaitForExit()
    if ($child.ExitCode -ne 0) { throw "$Label failed with exit code $($child.ExitCode)." }
    Write-Status 'completed' $Label
}

try {
    Wait-ForWindowAndIdle

    if (-not (Test-Path -LiteralPath $RawSource -PathType Container)) {
        throw "Raw source not found: $RawSource"
    }
    if (-not (Test-Path -LiteralPath $ApprovedPairsPath -PathType Leaf)) {
        Write-Status 'blocked_missing_approved_pairs' 'No approved pair file exists. Nothing was loaded or modified.'
        exit 0
    }

    $buildId = 'turbosparse-approved-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
    $bundle = Join-Path $Vault "$ModelId\$buildId"
    $edited = Join-Path $bundle 'source\edited'

    # Both are read-only preflights. The second confirms the pair schema/count,
    # raw source, and that the immutable output path does not already exist.
    Invoke-Checked 'approved-pair validation' $Py @((Join-Path $Tools 'validate_approved_calibration_pairs.py'), $ApprovedPairsPath)
    Invoke-Checked 'immutable rebuild preflight' $Py @((Join-Path $Tools 'preflight_turbosparse_rebuild.py'), '--source', $RawSource, '--pairs', $ApprovedPairsPath, '--output', $edited)

    # The vault creates a new bundle only; it never overwrites the 20260830b
    # exploratory checkpoint or any evidence tree.
    Invoke-Checked 'vault initialization' $Py @((Join-Path $Tools 'init_vault.py'), '--vault', $Vault, 'init')
    Invoke-Checked 'immutable bundle creation' $Py @((Join-Path $Tools 'init_vault.py'), '--vault', $Vault, 'create-bundle', '--model-id', $ModelId, '--build-id', $buildId)

    Invoke-Checked 'projected ablation into new immutable source' $Py @(
        (Join-Path $Tools 'abliterate_turbosparse_v2.py'), '--model', $RawSource,
        '--pairs', $ApprovedPairsPath, '--output', $edited, '--trust-remote-code'
    ) -GpuWork

    Invoke-Checked 'prompt-contract receipt' $Py @(
        (Join-Path $Tools 'capture_turbosparse_prompt_contract.py'), '--source', $edited,
        '--out', (Join-Path $bundle 'validation\prompt_contract.json')
    )

    # The pipeline performs C4-only calibration acquisition, a 4-bit activation
    # dump, and the ReLU/approved-pair lineage checks. It cannot start ComfyUI.
    Invoke-Checked 'public calibration manifest' 'pwsh.exe' @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Pipeline,
        '-ModelId', $ModelId, '-Stage', 'calib', '-Execute', '-Vault', $Vault,
        '-BuildId', $buildId, '-SourceDir', $edited
    )
    Invoke-Checked 'sparse activation profile' 'pwsh.exe' @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $Pipeline,
        '-ModelId', $ModelId, '-Stage', 'dump', '-Execute', '-Load4Bit', '-Vault', $Vault,
        '-BuildId', $buildId, '-SourceDir', $edited, '-ApprovedPairsPath', $ApprovedPairsPath
    ) -GpuWork

    if ($RunPredictorTraining) {
        # A deliberately bounded first pass. It is not a production-quality
        # claim; completion still requires conversion plus the strict JSON gate.
        Invoke-Checked 'guarded predictor training' 'pwsh.exe' @(
            '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Tools 'resume_calibration_guarded.ps1'),
            '-ModelId', $ModelId, '-Vault', $Vault, '-BuildId', $buildId,
            '-PredictorWorkspace', $bundle, '-StartLayer', '0', '-EndLayer', '31',
            '-WaitForCheckpointLayer', '-1', '-TrainSamples', '25000', '-PredictorRank', '256',
            '-TrainBatchSize', '256', '-TrainEpochs', '2', '-StartMaxC', "$StartMaxC", '-EmergencyC', "$EmergencyC"
        ) -GpuWork
        Write-Status 'awaiting_conversion_and_quality_gate' 'Predictors trained. Conversion and live two-turn JSON gate remain deliberately separate.' @{ bundle = $bundle }
    } else {
        Write-Status 'profile_complete_awaiting_training_profile' 'Immutable approved-pair edit and activation profile complete. Predictor training was not requested.' @{ bundle = $bundle }
    }
} catch {
    Write-Status 'failed_or_blocked' $_.Exception.Message
    exit 1
}
