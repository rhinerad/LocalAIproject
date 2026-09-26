<#
Run the smallest possible native PowerInfer mechanical gate for the locked
Bamboo-DPO Q4 candidate. This script is deliberately not a server launcher:
it starts one bounded main.exe process, captures the result, and exits.

It refuses unless the byte-verification report is valid, no ComfyUI listener
owns port 8188, no existing PowerInfer process is present, and the GPU is cool.
It does not touch the registry, router, proxy, picker, or candidate source.
#>
[CmdletBinding()]
param(
    [string]$CandidateRoot = 'A:\PowerInferModels\bamboo-dpo-7b\20260830-q4-runtime-intake',
    [string]$MainExe = 'A:\PowerInferBuild\bin\main.exe',
    [int]$VramBudgetGiB = 12,
    [int]$MaxTokens = 16
)

$ErrorActionPreference = 'Stop'
if ($VramBudgetGiB -lt 1 -or $VramBudgetGiB -gt 12) { throw 'VramBudgetGiB must be 1..12 for this isolated gate.' }
if ($MaxTokens -lt 1 -or $MaxTokens -gt 32) { throw 'MaxTokens must be 1..32 for this isolated gate.' }

$manifestPath = Join-Path $CandidateRoot 'manifest.json'
$verificationPath = Join-Path $CandidateRoot 'validation\bamboo_dpo_local_hash_verification.json'
$gguf = Join-Path $CandidateRoot 'source\gguf\bamboo-7b-dpo-v0.1.Q4_0.powerinfer.gguf'
$activation = Join-Path $CandidateRoot 'source\gguf\activation'
foreach ($path in @($manifestPath, $verificationPath, $gguf, $activation, $MainExe)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "Required path missing: $path" }
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$verification = Get-Content -LiteralPath $verificationPath -Raw | ConvertFrom-Json
if ($manifest.status -ne 'candidate' -or $manifest.profile -ne 'q4_runtime') { throw 'Candidate manifest is not the locked Q4 runtime receipt.' }
if (-not $verification.valid) { throw 'Local intake verification is not valid.' }
if (@(Get-ChildItem -LiteralPath $activation -Filter 'activation_*.pt' -File).Count -ne 32) { throw 'Expected exactly 32 activation files.' }
if (Get-NetTCPConnection -LocalPort 8188 -ErrorAction SilentlyContinue) { throw 'ComfyUI port 8188 is active; refuse to use GPU.' }
if (Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(main|server)$' }) { throw 'A native PowerInfer process is already active; refuse duplicate runner.' }
$nvidia = (Get-Command nvidia-smi -ErrorAction Stop).Source
$gpuLine = (& $nvidia --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>&1 | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($gpuLine)) { throw 'nvidia-smi returned no GPU status.' }
if ([int](($gpuLine -split ',')[0].Trim()) -ge 82) { throw "GPU temperature is unsafe: $gpuLine" }

$validation = Join-Path $CandidateRoot 'validation'
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$stdout = Join-Path $validation "bamboo_dpo_mechanical_gate_${stamp}.stdout.log"
$stderr = Join-Path $validation "bamboo_dpo_mechanical_gate_${stamp}.stderr.log"
$result = Join-Path $validation "bamboo_dpo_mechanical_gate_${stamp}.json"
$prompt = 'The following is a short factual completion. The capital of France is'
$args = @('--model', $gguf, '--vram-budget', "$VramBudgetGiB", '--ctx-size', '512', '--threads', '8', '--batch-size', '128', '--temp', '0', '--n-predict', "$MaxTokens", '--prompt', $prompt, '--simple-io')
$start = Get-Date
$previousPreference = $ErrorActionPreference
$repositoryRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$powerInferRoot = Join-Path $repositoryRoot 'external\PowerInfer'
$powerInferScripts = Join-Path $powerInferRoot '.venv\Scripts'
if (-not (Test-Path -LiteralPath (Join-Path $powerInferScripts 'python.exe'))) { throw "PowerInfer venv is missing: $powerInferScripts" }
$priorPath = $env:Path
$priorPythonPath = $env:PYTHONPATH
$ErrorActionPreference = 'Continue'
try {
    # The native loader calls the literal `python -m powerinfer` to calculate
    # the sparse split. Put the matching PowerInfer venv first, never Python's
    # unrelated system installation.
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
$afterGpu = (& $nvidia --query-gpu=temperature.gpu,utilization.gpu,memory.used --format=csv,noheader 2>&1 | Select-Object -First 1)
$outText = if (Test-Path -LiteralPath $stdout) { Get-Content -LiteralPath $stdout -Raw } else { '' }
$errText = if (Test-Path -LiteralPath $stderr) { Get-Content -LiteralPath $stderr -Raw } else { '' }
$sparseLoaded = $errText -match 'PowerInfer model loaded\. Sparse inference will be used\.'
$cudaLoaded = $errText -match 'using CUDA for GPU acceleration'
$splitFailed = $errText -match 'failed to generate gpu split|empty one will be used|No module named powerinfer'
$splitOffload = [regex]::Match($errText, 'offloaded\s+([0-9.]+)\s+MiB of FFN weights to GPU')
$ffnOffloadMib = if ($splitOffload.Success) { [double]$splitOffload.Groups[1].Value } else { 0.0 }
$mechanicalPass = ($exitCode -eq 0 -and $outText.Length -gt 0 -and $sparseLoaded -and $cudaLoaded -and -not $splitFailed -and $ffnOffloadMib -gt 0)
[ordered]@{
    schema_version = 'powerinfer-bamboo-mechanical-gate-v1'
    candidate_root = $CandidateRoot
    model_sha256 = (Get-FileHash -LiteralPath $gguf -Algorithm SHA256).Hash.ToLowerInvariant()
    validation_input = @{ verified = [bool]$verification.valid; activation_count = 32; prompt_kind = 'raw_completion'; prompt = $prompt; max_tokens = $MaxTokens; vram_budget_gib = $VramBudgetGiB }
    started_local = $start.ToString('o')
    finished_local = $finish.ToString('o')
    elapsed_seconds = [math]::Round(($finish - $start).TotalSeconds, 3)
    exit_code = $exitCode
    stdout_log = $stdout
    stderr_log = $stderr
    stdout_chars = $outText.Length
    stderr_chars = $errText.Length
    gpu_before = $gpuLine
    gpu_after = $afterGpu
    native_evidence = @{ sparse_model_loaded = $sparseLoaded; cuda_acceleration = $cudaLoaded; split_failure_detected = $splitFailed; ffn_offload_mib = $ffnOffloadMib }
    mechanical_pass = $mechanicalPass
    scope = 'single main.exe raw-completion smoke only; no server, registry, router, proxy, picker, or ComfyUI'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $result -Encoding utf8
Get-Content -LiteralPath $result -Raw
