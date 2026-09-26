# PowerInfer suite orchestrator.
# Wraps existing run_pipeline.ps1 stages. Does not replace dump/train.
#
# ReluLLaMA-7B (SparseLLM/ReluLLaMA-7B) is already plain ReLU: skip Orion-zhen.
# Abliterated SiLU Llama-3.1 fails relu-gate; ReLUfication is continued
# training, not a weight convert. -RunAbliteration is research-only and still
# fail-closed at relu-gate.
#
# Default is plan-only. Pass -Execute for intake/GPU/quantize/deletes.
#
# After a verified Q4_0 GGUF + activation_*.pt, deletes ONLY:
#   bundle\source\hf          (raw HF download)
#   bundle\source\ablit-fp16  (optional abliteration output)
# Never deletes activation/, predictor/, predictor_raw/, GGUF, manifests,
# logs, or changelog evidence. Vault policy has no delete API for those.

[CmdletBinding()]
param(
    [string[]]$Models = @('relu-llama-7b'),
    [string]$Vault = 'A:\PowerInferModels',
    [string]$PredictorWorkspace = '',
    [string]$AblitVenv = '',
    [string]$PowerInferVenv = '',
    [switch]$Execute,
    [switch]$StopOnError,
    [switch]$RunAbliteration,
    [switch]$UseSketchPredictor,
    [switch]$SkipDumpTrainIfPresent,
    [switch]$DeleteIntermediates
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if (-not $PSBoundParameters.ContainsKey('SkipDumpTrainIfPresent')) {
    $SkipDumpTrainIfPresent = $true
}

$Tools = $PSScriptRoot
$Pipeline = Join-Path $Tools 'run_pipeline.ps1'
$ModelsJson = Join-Path $Tools 'models.json'
$NvidiaSmi = Join-Path $env:SystemRoot 'System32\nvidia-smi.exe'
$LogDir = Join-Path $Vault 'suite-logs'
$Results = New-Object System.Collections.Generic.List[object]

if (-not (Test-Path -LiteralPath $Pipeline)) { throw "missing $Pipeline" }
if (-not (Test-Path -LiteralPath $ModelsJson)) { throw "missing $ModelsJson" }

$catalog = Get-Content -LiteralPath $ModelsJson -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Write-SuiteLog([string]$Message) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'), $Message
    Write-Host $line
    Add-Content -LiteralPath (Join-Path $LogDir 'batch_suite.log') -Value $line
}

function Get-Prop {
    param($Object, [string]$Name, $Default = $null)
    $p = $Object.PSObject.Properties[$Name]
    if ($null -eq $p) { return $Default }
    return $p.Value
}

function Get-GpuSnapshot {
    if (-not (Test-Path -LiteralPath $NvidiaSmi)) {
        throw "nvidia-smi not found: $NvidiaSmi"
    }
    $raw = & $NvidiaSmi '--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu' '--format=csv,noheader,nounits'
    return ($raw | Select-Object -First 1)
}

function Assert-GpuIdle {
    $snap = Get-GpuSnapshot
    Write-SuiteLog "GPU: $snap"
    $used = 0
    $bits = $snap.ToString().Split(',')
    if ($bits.Count -ge 2) { [void][int]::TryParse($bits[1].Trim(), [ref]$used) }
    if ($used -gt 2500) {
        throw "GPU looks busy ($used MiB used). Stop ComfyUI/Zing/other owners before -Execute."
    }
}

function Resolve-Target([string]$Name) {
    $t = Get-Prop $catalog.targets $Name
    if ($t) { return @{ Id = $Name; Spec = $t } }
    foreach ($prop in $catalog.targets.PSObject.Properties) {
        $hf = [string](Get-Prop $prop.Value 'hf_id' '')
        if ($hf -and $hf -eq $Name) {
            return @{ Id = $prop.Name; Spec = $prop.Value }
        }
    }
    throw "Unknown model '$Name'. Use a models.json id (relu-llama-7b, llama31-8b-abliterated-relu) or its hf_id. PowerInfer/ReluLLaMA-7B 404s; use SparseLLM/ReluLLaMA-7B."
}

function Invoke-Stage {
    param(
        [string]$ModelId,
        [string]$Stage,
        [string]$BuildId
    )
    $splat = @{
        ModelId = $ModelId
        Stage   = $Stage
        Vault   = $Vault
        BuildId = $BuildId
    }
    if ($PredictorWorkspace) { $splat['PredictorWorkspace'] = $PredictorWorkspace }
    if ($Execute) { $splat['Execute'] = $true }
    Write-SuiteLog "STAGE $ModelId $Stage"
    # In-process: this machine has Windows PowerShell 5.1, not pwsh.
    & $Pipeline @splat
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "stage $Stage failed for $ModelId (exit $LASTEXITCODE)"
    }
}

function Test-Q4Ready([string]$Root) {
    $outDir = Join-Path $Root 'output'
    $actDir = Join-Path $Root 'activation'
    $q4 = Get-ChildItem -LiteralPath $outDir -Filter '*.q4.powerinfer.gguf' -ErrorAction SilentlyContinue |
        Select-Object -First 1
    $acts = @()
    if (Test-Path -LiteralPath $actDir) {
        $acts = @(Get-ChildItem -LiteralPath $actDir -Filter 'activation_*.pt' -ErrorAction SilentlyContinue)
    }
    if (-not $q4 -or $q4.Length -lt 1MB) { return $false }
    if ($acts.Count -lt 1) { return $false }
    return $true
}

function Remove-Intermediates([string]$Bundle) {
    if (-not $DeleteIntermediates) {
        Write-SuiteLog "keeping intermediates (pass -DeleteIntermediates to drop source\\hf and source\\ablit-fp16 after Q4_0)"
        return
    }
    $raw = Join-Path $Bundle 'source\hf'
    $ablit = Join-Path $Bundle 'source\ablit-fp16'
    foreach ($path in @($raw, $ablit)) {
        if (Test-Path -LiteralPath $path) {
            Write-SuiteLog "DELETE intermediate $path"
            Remove-Item -LiteralPath $path -Recurse -Force
        }
    }
}

function Invoke-OptionalAbliteration([string]$ModelId, [string]$Bundle, $Spec) {
    if (-not $RunAbliteration) { return }
    $needs = [bool](Get-Prop $Spec 'requires_relufication' $false)
    $act = [string](Get-Prop $Spec 'expected_hidden_act' '')
    if (-not $needs) {
        Write-SuiteLog "skip Orion-zhen for $ModelId (already expected_hidden_act=$act)"
        return
    }
    if (-not $AblitVenv) {
        throw "$ModelId requested -RunAbliteration but -AblitVenv was not set (.venv-ablit)."
    }
    $py = Join-Path $AblitVenv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { throw "missing abliteration python: $py" }
    Write-SuiteLog "WARNING: Orion-zhen abliteration does not turn SiLU into ReLU. relu-gate will still fail unless the source is already ReLU/ReGLU."
    $out = Join-Path $Bundle 'source\ablit-fp16'
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $cli = Get-Command 'llm-abliteration' -ErrorAction SilentlyContinue
    if (-not $cli) {
        throw "llm-abliteration CLI not on PATH. Install Orion-zhen in $AblitVenv or omit -RunAbliteration and pass a ReLU checkpoint via models.json hf_id / -SourceDir."
    }
    $hf = Join-Path $Bundle 'source\hf'
    & $cli --model $hf --output $out
    if ($LASTEXITCODE -ne 0) { throw "llm-abliteration failed for $ModelId" }
}

function Get-ExistingEvidenceRoot([string]$ModelId, [string]$Bundle) {
    if ($PredictorWorkspace -and (Test-Path -LiteralPath $PredictorWorkspace)) {
        return $PredictorWorkspace
    }
    return $Bundle
}

Write-SuiteLog "batch_suite start vault=$Vault execute=$Execute models=$($Models -join ',')"
try {
    Write-SuiteLog (Get-GpuSnapshot)
} catch {
    Write-SuiteLog "nvidia-smi unavailable: $($_.Exception.Message)"
}
if ($Execute) { Assert-GpuIdle }

foreach ($name in $Models) {
    $row = [ordered]@{
        model  = $name
        id     = ''
        status = 'pending'
        reason = ''
        q4     = ''
    }
    try {
        $resolved = Resolve-Target $name
        $id = [string]$resolved.Id
        $spec = $resolved.Spec
        $row.id = $id
        if (Get-Prop $spec 'retired' $false) {
            throw "retired target $id : $(Get-Prop $spec 'retired_reason' 'retired')"
        }
        $build = Get-Date -Format 'yyyyMMdd-HHmmss'
        $bundle = Join-Path $Vault "$id\$build"
        $evidence = Get-ExistingEvidenceRoot $id $bundle

        $hfId = [string](Get-Prop $spec 'hf_id' '')
        if ($hfId -eq 'PowerInfer/ReluLLaMA-7B') {
            throw [string](Get-Prop $spec 'hf_id_note' 'PowerInfer/ReluLLaMA-7B 404s')
        }

        Invoke-Stage $id 'show' $build
        if (-not $Execute) {
            $row.status = 'planned'
            $row.reason = 'no -Execute; plan only'
            $Results.Add([pscustomobject]$row)
            continue
        }

        Invoke-Stage $id 'intake' $build
        Invoke-OptionalAbliteration $id $bundle $spec
        Invoke-Stage $id 'relu-gate' $build
        Invoke-Stage $id 'calib' $build

        $act0 = Join-Path $evidence 'activation\activation_0.pt'
        $needDump = -not ($SkipDumpTrainIfPresent -and (Test-Path -LiteralPath $act0))
        if ($UseSketchPredictor) {
            Write-SuiteLog "Using sketch generate_predictor.py (NOT production dump/train)"
            $py = if ($PowerInferVenv) { Join-Path $PowerInferVenv 'Scripts\python.exe' } else { 'py' }
            $src = Join-Path $bundle 'source\hf'
            & $py (Join-Path $Tools 'generate_predictor.py') --model $src --out-predictors (Join-Path $evidence 'predictor_raw') --out-activation (Join-Path $evidence 'activation')
            if ($LASTEXITCODE -ne 0) { throw 'generate_predictor.py failed' }
        } elseif ($needDump) {
            Invoke-Stage $id 'dump' $build
            Invoke-Stage $id 'train' $build
        } else {
            Write-SuiteLog "skip dump; activation evidence present at $act0"
            Invoke-Stage $id 'train' $build
        }

        Invoke-Stage $id 'convert' $build
        Invoke-Stage $id 'quantize' $build
        Invoke-Stage $id 'package' $build

        $readyRoot = $evidence
        if (-not (Test-Q4Ready $readyRoot)) {
            throw "Q4_0 or activation_*.pt missing after package; refusing to delete intermediates"
        }
        Remove-Intermediates $bundle
        $row.status = 'ok'
        $q4hit = Get-ChildItem -LiteralPath (Join-Path $readyRoot 'output') -Filter '*.q4.powerinfer.gguf' | Select-Object -First 1
        $row.q4 = [string]$q4hit.FullName
        Write-SuiteLog "OK $id -> $($row.q4)"
    } catch {
        $row.status = 'failed'
        $row.reason = $_.Exception.Message
        Write-SuiteLog "FAIL $($row.id) $($row.reason)"
        if ($StopOnError) { throw }
    }
    $Results.Add([pscustomobject]$row)
}

$summary = Join-Path $LogDir ('summary-{0}.json' -f (Get-Date -Format 'yyyyMMdd-HHmmss'))
$Results | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $summary -Encoding utf8
Write-SuiteLog "summary $summary"
$Results | Format-Table -AutoSize | Out-String | Write-Host
