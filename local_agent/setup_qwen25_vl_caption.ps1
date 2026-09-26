# Explicit setup for the local Qwen2.5-VL caption model. It is never run by the
# launcher, media watcher, or server. Existing model files are left untouched.
[CmdletBinding()]
param(
    [switch]$Download
)

$ErrorActionPreference = 'Stop'
$Repo = 'mradermacher/Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF'
$ModelRemoteName = 'Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.gguf'
$ProjectorRemoteName = 'Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.gguf'
$ModelName = 'Qwen2.5-VL-7B-NSFW-Caption-V4.Q4_K_M.local.gguf'
$ProjectorName = 'Qwen2.5-VL-7B-NSFW-Caption-V4.mmproj-Q8_0.local.gguf'
$ModelBytes = 4684339808
$ProjectorBytes = 732298784
$ModelSha256 = 'e6987f2c5b227f1903d44a7766c119000e7a779b043f4ce6c426c39d76fa845d'
$ProjectorSha256 = '470186df4f8ea3b3fed49482a382edf118e539d9b7074177c51266f00c8262c1'
$TargetDir = 'A:\Users\rhine\ComfyUI-Shared\models\LLM\GGUF\mradermacher\Qwen2.5-VL-7B-NSFW-Caption-V4-GGUF'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Modelfile = Join-Path $Here 'Modelfile.qwen25-vl-nsfw-caption'
$Ollama = 'A:\Users\rhine\AppData\Local\Programs\Ollama\ollama.exe'

function Test-ModelFile([string]$Path, [Int64]$MinimumBytes) {
    return (Test-Path -LiteralPath $Path) -and ((Get-Item -LiteralPath $Path).Length -eq $MinimumBytes)
}

function Test-ModelSha256([string]$Path, [string]$Expected) {
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    return $actual -eq $Expected.ToLowerInvariant()
}

function Get-HuggingFaceFile([string]$RemoteName, [string]$Name, [Int64]$MinimumBytes) {
    $Destination = Join-Path $TargetDir $Name
    if (Test-ModelFile $Destination $MinimumBytes) {
        Write-Host "  already present: $Name" -ForegroundColor Green
        return
    }
    $Resume = Test-Path -LiteralPath $Destination
    if ($Resume) {
        $ExistingBytes = (Get-Item -LiteralPath $Destination).Length
        if ($ExistingBytes -le 0) {
            throw "Refusing to replace an empty unexpected existing file: $Destination"
        }
        Write-Host "  resuming $Name from $ExistingBytes bytes ..." -ForegroundColor Cyan
    }
    # Braces are required here: without them PowerShell can treat the question
    # mark as part of the variable expression and issue a subtly malformed URL.
    $Url = "https://huggingface.co/${Repo}/resolve/main/${RemoteName}?download=true"
    Write-Host "  downloading $RemoteName as $Name ..." -ForegroundColor Cyan
    $CurlArgs = @('--fail', '--location', '--retry', '3', '--retry-delay', '5')
    if ($Resume) { $CurlArgs += @('--continue-at', '-') }
    $CurlArgs += @('--output', $Destination, $Url)
    & curl.exe @CurlArgs
    if ($LASTEXITCODE -ne 0 -or -not (Test-ModelFile $Destination $MinimumBytes)) {
        throw "Download did not produce the expected file size: $Destination"
    }
}

Write-Host 'Qwen2.5-VL NSFW Caption V4 local setup' -ForegroundColor Cyan
Write-Host 'Required download: about 5.33 GB (4.68 GB Q4_K_M model + 0.70 GB Q8_0 projector).' -ForegroundColor Yellow
Write-Host "Target directory: $TargetDir"

if ($Download) {
    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
    Get-HuggingFaceFile $ModelRemoteName $ModelName $ModelBytes
    # The version-matched Q8_0 projector is 732298784 bytes. The bound must
    # stay exact and match capabilities.py.
    Get-HuggingFaceFile $ProjectorRemoteName $ProjectorName $ProjectorBytes
}

$ModelPath = Join-Path $TargetDir $ModelName
$ProjectorPath = Join-Path $TargetDir $ProjectorName
if (-not (Test-ModelFile $ModelPath $ModelBytes) -or -not (Test-ModelFile $ProjectorPath $ProjectorBytes)) {
    Write-Host 'Files are not both present. Re-run with -Download when the 5.33 GB download is authorised.' -ForegroundColor Yellow
    exit 2
}
if (-not (Test-ModelSha256 $ModelPath $ModelSha256) -or -not (Test-ModelSha256 $ProjectorPath $ProjectorSha256)) {
    Write-Host 'SHA-256 mismatch against the pinned Hugging Face LFS oid. Refusing this pair.' -ForegroundColor Red
    exit 3
}
Write-Host 'Ready. The local-agent launcher loads both files through the CUDA llama.cpp runtime on 127.0.0.1:11436.' -ForegroundColor Green
Write-Host 'Ollama import is intentionally not attempted: this GGUF needs llama.cpp compatibility patches that Ollama rejects.' -ForegroundColor Yellow
Write-Host 'Restart START_LOCAL_AGENT_GUI.ps1 only when you are ready to reload the local agent.' -ForegroundColor Green
