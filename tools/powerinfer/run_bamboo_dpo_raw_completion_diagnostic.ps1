<#
Run exactly one source-backed raw-completion diagnostic for the locked
Bamboo-DPO Q4 candidate. This is deliberately not a chat or quality gate.

The frozen model code documents a plain prompt -> tokenizer -> generate path.
It does not document a chat wrapper. The script must be invoked with -Execute,
never starts a server, and preserves a timestamped receipt beside validation
evidence. It does not alter the candidate, registry, router, proxy, picker,
or ComfyUI.
#>
[CmdletBinding()]
param(
    [switch]$Execute,
    [string]$CandidateRoot = 'A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake',
    [string]$MainExe = 'A:\PowerInferBuild\bin\main.exe',
    [int]$VramBudgetGiB = 12,
    [int]$MaxTokens = 48,
    [string]$Prompt = 'Hey, are you conscious? Can you talk to me?'
)

$ErrorActionPreference = 'Stop'

function Get-Sha256Hex {
    param([Parameter(Mandatory = $true)][string]$Path)
    # Do not depend on Get-FileHash being exposed by the host shell. The
    # bounded runner is also invoked by a detached Windows PowerShell process,
    # where that cmdlet was unavailable despite being present in the interactive
    # shell. .NET's SHA256 implementation is available in both hosts.
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $hasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            return ([System.BitConverter]::ToString($hasher.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
        } finally {
            $hasher.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

if (-not $Execute) {
    throw 'Refusing to load a model. Re-run with -Execute only after a fresh GPU-owner decision.'
}
if ($VramBudgetGiB -lt 1 -or $VramBudgetGiB -gt 12) { throw 'VramBudgetGiB must be 1..12.' }
if ($MaxTokens -lt 1 -or $MaxTokens -gt 64) { throw 'MaxTokens must be 1..64.' }
if ([string]::IsNullOrWhiteSpace($Prompt) -or $Prompt.Length -gt 512) { throw 'Prompt must be 1..512 characters.' }

$manifestPath = Join-Path $CandidateRoot 'manifest.json'
$verificationPath = Join-Path $CandidateRoot 'validation\bamboo_dpo_local_hash_verification.json'
$validation = Join-Path $CandidateRoot 'validation'
$gguf = Join-Path $CandidateRoot 'source\gguf\bamboo-7b-dpo-v0.1.Q4_0.powerinfer.gguf'
$activation = Join-Path $CandidateRoot 'source\gguf\activation'
foreach ($path in @($manifestPath, $verificationPath, $validation, $gguf, $activation, $MainExe)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath $verificationPath -Raw | ConvertFrom-Json
if ($manifest.status -ne 'candidate' -or $manifest.profile -ne 'q4_runtime') { throw 'Candidate manifest is not the locked Q4 runtime receipt.' }
if (-not $verification.valid) { throw 'Local intake verification is not valid.' }
if (@(Get-ChildItem -LiteralPath $activation -Filter 'activation_*.pt' -File).Count -ne 32) { throw 'Expected exactly 32 activation files.' }
$contract = Get-ChildItem -LiteralPath $validation -Filter 'bamboo_dpo_prompt_contract_addendum_*.json' -File |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($null -eq $contract) { throw 'No source-backed prompt-contract addendum is present.' }
$contractData = Get-Content -LiteralPath $contract.FullName -Raw | ConvertFrom-Json
if (-not $contractData.raw_completion_diagnostic_allowed -or $contractData.chat_routing_allowed -or $contractData.instruction_quality_gate_allowed) {
    throw 'Prompt contract does not permit the strictly raw-completion-only diagnostic.'
}
if (Get-NetTCPConnection -LocalPort 8188 -ErrorAction SilentlyContinue) { throw 'ComfyUI port 8188 is active; refuse to use GPU.' }
if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(main|server)$' }) { throw 'A native PowerInfer process is already active; refuse duplicate runner.' }
$nvidia = (Get-Command nvidia-smi -ErrorAction Stop).Source
$gpuBefore = (& $nvidia --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>&1 | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($gpuBefore)) { throw 'nvidia-smi returned no GPU status.' }
if ([int](($gpuBefore -split ',')[0].Trim()) -ge 82) { throw "GPU temperature is unsafe: $gpuBefore" }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $validation "bamboo_dpo_raw_completion_${stamp}.stdout.log"
$stderr = Join-Path $validation "bamboo_dpo_raw_completion_${stamp}.stderr.log"
$result = Join-Path $validation "bamboo_dpo_raw_completion_${stamp}.json"
$args = @('--model', $gguf, '--vram-budget', "$VramBudgetGiB", '--ctx-size', '512', '--threads', '8', '--batch-size', '128', '--temp', '0', '--n-predict', "$MaxTokens", '--prompt', $Prompt, '--simple-io')
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powerInferRoot = Join-Path $repositoryRoot 'external\PowerInfer'
$powerInferScripts = Join-Path $powerInferRoot '.venv\Scripts'
if (-not (Test-Path -LiteralPath (Join-Path $powerInferScripts 'python.exe'))) { throw "PowerInfer venv is missing: $powerInferScripts" }
$priorPath = $env:Path
$priorPythonPath = $env:PYTHONPATH
$start = Get-Date
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
try {
    $env:Path = $powerInferScripts + ';' + $priorPath
    $env:PYTHONPATH = $PSScriptRoot + ';' + $powerInferRoot
    & $MainExe @args 1> $stdout 2> $stderr
    $exitCode = $LASTEXITCODE
} finally {
    $env:Path = $priorPath
    $env:PYTHONPATH = $priorPythonPath
    $ErrorActionPreference = $previousPreference
}
$finish = Get-Date
$gpuAfter = (& $nvidia --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>&1 | Select-Object -First 1)
$outText = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw } else { '' }
$errText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw } else { '' }
$sparseLoaded = $errText -match 'PowerInfer model loaded\. Sparse inference will be used\.'
$cudaLoaded = $errText -match 'using CUDA for GPU acceleration'
$splitFailed = $errText -match 'failed to generate gpu split|empty one will be used|No module named powerinfer'
$splitOffload = [regex]::Match($errText, 'offloaded\s+([0-9.]+)\s+MiB of FFN weights to GPU')
$ffnOffloadMib = if ($splitOffload.Success) { [double]$splitOffload.Groups[1].Value } else { 0.0 }
[ordered]@{
    schema_version = 'powerinfer-bamboo-raw-completion-diagnostic-v1'
    candidate_root = $CandidateRoot
    model_sha256 = Get-Sha256Hex -Path $gguf
    source_contract_receipt = $contract.FullName
    purpose = 'source-backed bounded raw-completion diagnostic only; not a chat or instruction-quality test'
    prompt = $Prompt
    max_tokens = $MaxTokens
    vram_budget_gib = $VramBudgetGiB
    started_local = $start.ToString('o')
    finished_local = $finish.ToString('o')
    elapsed_seconds = [math]::Round(($finish - $start).TotalSeconds, 3)
    exit_code = $exitCode
    stdout_log = $stdout
    stderr_log = $stderr
    stdout_chars = $outText.Length
    stderr_chars = $errText.Length
    gpu_before = $gpuBefore
    gpu_after = $gpuAfter
    native_evidence = @{ sparse_model_loaded = $sparseLoaded; cuda_acceleration = $cudaLoaded; split_failure_detected = $splitFailed; ffn_offload_mib = $ffnOffloadMib }
    completed_unscored = ($exitCode -eq 0 -and $outText.Length -gt 0 -and $sparseLoaded -and $cudaLoaded -and -not $splitFailed -and $ffnOffloadMib -gt 0)
    promotion_allowed = $false
    scope = 'one main.exe process; no server, registry, router, proxy, picker, model promotion, or ComfyUI'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $result -Encoding utf8
Get-Content -LiteralPath $result -Raw
