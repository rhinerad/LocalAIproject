# Opt-in CUDA llama.cpp runtime for Qwen2.5-VL. Never run automatically.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$Root = 'A:\Users\rhine\ComfyUI-Shared\runtimes\llama.cpp-cuda'
$Zip = Join-Path $Root 'llama-b10516-bin-win-cuda-12.4-x64.zip'
$CudaZip = Join-Path $Root 'cudart-llama-bin-win-cuda-12.4-x64.zip'
$Url = 'https://github.com/ggml-org/llama.cpp/releases/download/b10516/llama-b10516-bin-win-cuda-12.4-x64.zip'
$CudaUrl = 'https://github.com/ggml-org/llama.cpp/releases/download/b10516/cudart-llama-bin-win-cuda-12.4-x64.zip'
$ExpectedSha256 = '96d64faeb5b8e655341f32b26ad3e51fbea8bff0bc8120ad3dbffdc0b05b8ad3'
$ExpectedCudaSha256 = '8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6'
$Server = Join-Path $Root 'llama-server.exe'
if (Test-Path -LiteralPath $Server) { Write-Host "CUDA llama.cpp already present: $Server"; exit 0 }
New-Item -ItemType Directory -Force -Path $Root | Out-Null
function Get-VerifiedArchive([string]$Path, [string]$DownloadUrl, [string]$ExpectedHash) {
    if (-not (Test-Path -LiteralPath $Path)) {
        Write-Host "Downloading $(Split-Path -Leaf $Path) ..." -ForegroundColor Cyan
        & curl.exe --fail --location --retry 3 --output $Path $DownloadUrl
        if ($LASTEXITCODE -ne 0) { throw "Download failed: $Path" }
    }
    if ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
        throw "Archive checksum mismatch: $Path"
    }
}
Write-Host 'Installing official CUDA 12.4 llama.cpp binary and CUDA runtime DLLs (about 612 MB total) ...' -ForegroundColor Cyan
Get-VerifiedArchive $Zip $Url $ExpectedSha256
Get-VerifiedArchive $CudaZip $CudaUrl $ExpectedCudaSha256
Expand-Archive -LiteralPath $Zip -DestinationPath $Root
Expand-Archive -LiteralPath $CudaZip -DestinationPath $Root
if (-not (Test-Path -LiteralPath $Server)) { throw "llama-server.exe missing after extraction: $Server" }
Write-Host 'CUDA llama.cpp runtime ready.' -ForegroundColor Green
