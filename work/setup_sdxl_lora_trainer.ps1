[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Verify,
    [string]$TrainerRoot = 'A:\Users\rhine\kohya_ss',
    [string]$EnvironmentName = '.venv-local-agent'
)

$ErrorActionPreference = 'Stop'
$venv = Join-Path $TrainerRoot $EnvironmentName
$python = Join-Path $venv 'Scripts\python.exe'
$trainScript = Join-Path $TrainerRoot 'sd-scripts\sdxl_train_network.py'

if (-not (Test-Path -LiteralPath $TrainerRoot)) { throw "Kohya directory is missing: $TrainerRoot" }
if (-not (Test-Path -LiteralPath $trainScript)) { throw "SDXL trainer is missing: $trainScript" }

if ($Install) {
    if (-not (Test-Path -LiteralPath $venv)) {
        # Kohya requires Python >=3.10,<3.12. This never alters the legacy .venv.
        & uv python install 3.11
        if ($LASTEXITCODE -ne 0) { throw 'Could not install managed Python 3.11.' }
        & uv venv --python 3.11 $venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create the isolated environment.' }
    } elseif (-not (Test-Path -LiteralPath $python)) {
        throw "Refusing to use incomplete environment directory: $venv"
    }

    # uv venv can omit pip on some managed Windows interpreter builds.
    & $python -m ensurepip --upgrade
    if ($LASTEXITCODE -ne 0) { throw 'Could not bootstrap pip in the isolated environment.' }
    & $python -m pip install --upgrade pip setuptools wheel
    if ($LASTEXITCODE -ne 0) { throw 'Could not update isolated-environment packaging tools.' }
    # Kohya's requirements include a relative editable ./sd-scripts entry.
    Push-Location $TrainerRoot
    try {
        & $python -m pip install -r 'requirements_pytorch_windows.txt'
        if ($LASTEXITCODE -ne 0) { throw 'Kohya dependency installation failed.' }
    } finally {
        Pop-Location
    }
    Write-Host "Created isolated SDXL LoRA environment: $venv"
}

if ($Verify) {
    if (-not (Test-Path -LiteralPath $python)) { throw "Isolated environment not found: $venv. Run with -Install first." }
    & $python -c "import torch; import accelerate; import diffusers; print({'python': __import__('sys').version.split()[0], 'torch': torch.__version__, 'cuda_available': torch.cuda.is_available(), 'cuda': torch.version.cuda, 'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None})"
    if ($LASTEXITCODE -ne 0) { throw 'Core SDXL package import check failed.' }
    # Kohya's help text includes characters that the legacy Windows cp1252
    # console cannot encode. Force UTF-8 only for this non-training CLI probe.
    $oldUtf8 = $env:PYTHONUTF8
    $oldEncoding = $env:PYTHONIOENCODING
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    Push-Location $TrainerRoot
    try {
        & $python $trainScript --help *> $null
    } finally {
        Pop-Location
        $env:PYTHONUTF8 = $oldUtf8
        $env:PYTHONIOENCODING = $oldEncoding
    }
    if ($LASTEXITCODE -ne 0) { throw 'SDXL trainer help check failed.' }
    Write-Host 'SDXL LoRA trainer preflight passed. No model was loaded and no training was started.'
}

if (-not $Install -and -not $Verify) {
    Write-Host 'Safe usage: -Install creates a separate environment; -Verify checks imports and trainer CLI without loading a model.'
}
