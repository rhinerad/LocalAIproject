# Native Windows PowerInfer conversion pipeline.
# Default target: installed Visual Studio x64 + CUDA 12.8+ + -DLLAMA_CUBLAS=ON + sm_120.
# Does not wire the result into the local-agent picker. GPU stages require -Execute.
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('relu-llama-7b', 'prosparse-7b', 'llama31-8b-abliterated-relu', 'turbosparse-mistral-instruct')]
    [string]$ModelId,

    [ValidateSet('show', 'setup', 'intake', 'relu-gate', 'calib', 'dump', 'train', 'convert', 'quantize', 'package', 'validate', 'bench', 'all')]
    [string]$Stage = 'show',

    [string]$SourceDir = '',
    [string]$Vault = '',
    [string]$BuildId = '',
    [string]$HfId = '',
    [Nullable[double]]$VramBudget = $null,
    [int]$Threads = 8,
    [string]$CudaArch = '120',
    [Nullable[int]]$TrainSamples = $null,
    [Nullable[int]]$PredictorRank = $null,
    [Nullable[int]]$TrainBatchSize = $null,
    [Nullable[int]]$TrainEpochs = $null,
    [int]$LayerStart = 0,
    [Nullable[int]]$LayerCount = $null,
    # Optional writable checkpoint workspace. Use only when a read-only vault
    # holds the large activation mmaps; this never moves or rewrites them.
    [string]$PredictorWorkspace = '',
    # Required for source checkpoints whose refusal-direction edit depends on
    # human-reviewed contrastive pairs. This is an evidence gate; it never
    # treats a JSONL file as a model-quality result.
    [string]$ApprovedPairsPath = '',
    [string]$PowerInferDir = '',
    [string]$VisualStudioGenerator = '',
    [switch]$Execute,
    [switch]$Load4Bit,
    [switch]$SkipGpuPreflight,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Tools = $PSScriptRoot
$Repo = (Resolve-Path (Join-Path $Tools '..\..')).Path
$External = Join-Path $Repo 'external'
if (-not $PowerInferDir) { $PowerInferDir = Join-Path $External 'PowerInfer' }
$VenvPython = Join-Path $PowerInferDir '.venv\Scripts\python.exe'
if (Test-Path $VenvPython) {
    $Py = $VenvPython
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $Py = 'py'
} else {
    $Py = 'python'
}
$env:PYTHONPATH = $Tools

function Get-Target {
    $reg = Get-Content -Raw -LiteralPath (Join-Path $Tools 'models.json') | ConvertFrom-Json
    $t = $reg.targets | Select-Object -ExpandProperty $ModelId
    if (-not $t) { throw "unknown model id $ModelId" }
    return $t, $reg.defaults
}

function Get-Vault {
    if ($Vault) { return $Vault }
    $resolved = & $Py -c "from vault import default_vault_path; print(default_vault_path())"
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($resolved)) {
        throw "failed to resolve vault path from vault.default_vault_path()"
    }
    return $resolved.Trim()
}

function Get-BuildId {
    if ($BuildId) { return $BuildId }
    return (Get-Date -Format 'yyyyMMdd-HHmmss')
}

function Get-Source([object]$Target, [string]$Bundle) {
    if ($SourceDir) {
        if (-not (Test-Path -LiteralPath $SourceDir)) { throw "SourceDir not found: $SourceDir" }
        return (Resolve-Path -LiteralPath $SourceDir).Path
    }
    $staged = Join-Path $Bundle 'source\hf'
    if (Test-Path -LiteralPath (Join-Path $staged 'config.json')) { return $staged }
    return $null
}

function Invoke-Py {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)
    Write-Host "+ $Py $($Args -join ' ')" -ForegroundColor DarkGray
    & $Py @Args
    if ($LASTEXITCODE -ne 0) { throw "python failed: $Args" }
}

function Assert-Execute($needGpu) {
    if (-not $Execute) {
        throw "Refusing GPU/download/build work without -Execute. Re-run with -Execute, or use -Stage show."
    }
    if ($needGpu -and -not $SkipGpuPreflight) {
        Invoke-Py (Join-Path $Tools 'check_gpu_preflight.py')
    }
}

function Resolve-NativeToolchain {
    # Fail before cloning or installing Python packages. CUDA 12.8's Windows
    # host-compiler support ends at VS 2022; VS 2026's cudafe++ crashes even
    # when nvcc is given its unsupported-compiler override.
    $nvcc = Get-Command nvcc -ErrorAction SilentlyContinue
    $nvccPath = if ($nvcc) { $nvcc.Source } else { $null }
    if (-not $nvccPath) {
        $cudaRoots = @()
        if ($env:CUDA_PATH) { $cudaRoots += $env:CUDA_PATH }
        $cudaBase = 'C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA'
        if (Test-Path -LiteralPath $cudaBase) {
            $cudaRoots += Get-ChildItem -LiteralPath $cudaBase -Directory |
                Sort-Object Name -Descending | ForEach-Object FullName
        }
        $nvccPath = $cudaRoots | ForEach-Object { Join-Path $_ 'bin\nvcc.exe' } |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    }
    if (-not $nvccPath) { throw 'nvcc was not found. Install CUDA Toolkit 12.8+ and use a VS 2022 x64 developer shell.' }
    $cudaBin = Split-Path -Parent $nvccPath
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) {
        throw 'Visual Studio Installer (vswhere.exe) was not found. Install Visual Studio 2022 Build Tools with Desktop development with C++.'
    }
    $vs2022 = (& $vswhere -latest -products * -version '[17.0,18.0)' -property installationPath | Select-Object -First 1).Trim()
    if ([string]::IsNullOrWhiteSpace($vs2022)) {
        throw 'PowerInfer CUDA build requires Visual Studio 2022 (17.x) x64 with Desktop development with C++. Visual Studio 2026 alone is unsupported by CUDA 12.8; install VS 2022 side-by-side, then rerun setup.'
    }
    if ($VisualStudioGenerator -and $VisualStudioGenerator -ne 'Ninja') {
        throw "PowerInfer CUDA build uses Ninja from Visual Studio 2022; received unsupported generator '$VisualStudioGenerator'."
    }
    $cmakeCandidate = Join-Path $vs2022 'Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
    $cmakePath = if (Test-Path -LiteralPath $cmakeCandidate) {
        $cmakeCandidate
    } else {
        $fallbackCmake = Get-Command cmake.exe -ErrorAction SilentlyContinue
        if ($fallbackCmake) { $fallbackCmake.Source } else { $null }
    }
    if (-not $cmakePath) { throw 'cmake was not found in the Visual Studio 2022 tree or on PATH.' }
    $ninjaPath = Join-Path $vs2022 'Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe'
    $devCmdPath = Join-Path $vs2022 'Common7\Tools\VsDevCmd.bat'
    if (-not (Test-Path -LiteralPath $ninjaPath)) { throw "Visual Studio 2022 Ninja was not found: $ninjaPath" }
    if (-not (Test-Path -LiteralPath $devCmdPath)) { throw "Visual Studio 2022 developer command file was not found: $devCmdPath" }
    return [pscustomobject]@{
        NvccPath = $nvccPath
        CmakePath = $cmakePath
        NinjaPath = $ninjaPath
        VsDevCmdPath = $devCmdPath
        Generator = 'Ninja'
    }
}

function Invoke-VaultInit {
    # vault.init_vault() is the only place that enforces "outside the repo",
    # writes the vault's own .gitignore (keys/, private/, scratch/, *.gguf,
    # *.mmap, *.pt), and records vault.json. Nothing else in this script did
    # this before, so a no-D:-drive machine could silently write GGUFs and
    # activation tensors straight into the git tree with no .gitignore
    # protecting them. Not called for -Stage show, so the preview stays a
    # pure read: no directories, no .gitignore, no refusal on that path.
    $probe = & $Py -c "from pathlib import Path; from vault import init_vault; init_vault(Path(r'$VaultRoot')); print('ok')" 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "vault init refused: $probe`nSet -Vault or `$env:POWERINFER_VAULT to a path outside this repository."
    }
}

$Target, $Defaults = Get-Target
$VaultRoot = Get-Vault
$Bid = Get-BuildId
$Bundle = Join-Path $VaultRoot "$ModelId\$Bid"
$ArtifactRoot = if ($PredictorWorkspace) { $PredictorWorkspace } else { $Bundle }
$Source = Get-Source $Target $Bundle
# Windows' compiler can fail on the canonical repository's deep source path.
# Keep source code where it was cloned, but compile through short A: aliases.
# Existing VS 2026/long-path build caches are deliberately preserved as evidence.
$NativeDriveRoot = [System.IO.Path]::GetPathRoot($Repo)
$NativeSourceDir = if ($env:POWERINFER_NATIVE_SOURCE) { $env:POWERINFER_NATIVE_SOURCE } else { Join-Path $NativeDriveRoot 'PowerInferNative' }
$NativeBuildDir = if ($env:POWERINFER_NATIVE_BUILD) { $env:POWERINFER_NATIVE_BUILD } else { Join-Path $NativeDriveRoot 'PowerInferBuild' }
$MainExe = Join-Path $NativeBuildDir 'bin\main.exe'
$ServerExe = Join-Path $NativeBuildDir 'bin\server.exe'
$QuantizeExe = Join-Path $NativeBuildDir 'bin\quantize.exe'
$Gguf = Join-Path $ArtifactRoot "output\$ModelId.powerinfer.gguf"
$Q4 = Join-Path $ArtifactRoot "output\$ModelId.q4.powerinfer.gguf"
$VocabArgs = @()
if ($Target.vocabtype -eq 'bpe') { $VocabArgs = @('--vocabtype', 'bpe') }
$EffectiveTrainSamples = if ($null -ne $TrainSamples) { $TrainSamples } else { [int]$Defaults.max_samples }
$EffectivePredictorRank = if ($null -ne $PredictorRank) { $PredictorRank } else { [int]$Defaults.predictor_rank }
$EffectiveTrainBatchSize = if ($null -ne $TrainBatchSize) { $TrainBatchSize } else { [int]$Defaults.train_batch_size }
$EffectiveTrainEpochs = if ($null -ne $TrainEpochs) { $TrainEpochs } else { [int]$Defaults.train_epochs }
$EffectiveLayerCount = if ($null -ne $LayerCount) { $LayerCount } else { [int]$Target.num_hidden_layers }
if ($LayerStart -lt 0 -or $EffectiveLayerCount -lt 1 -or ($LayerStart + $EffectiveLayerCount) -gt $Target.num_hidden_layers) {
    throw "invalid training layer range: start=$LayerStart count=$EffectiveLayerCount for $($Target.num_hidden_layers) layers"
}
if ($EffectiveTrainSamples -lt 1 -or $EffectiveTrainSamples -gt [int]$Defaults.max_samples) {
    throw "TrainSamples must be between 1 and $($Defaults.max_samples)"
}

function Show-Plan {
    $resolvedSource = if ($Source) {
        $Source
    } elseif ($HfId) {
        "intake will fetch $HfId"
    } elseif ($Target.hf_id) {
        "intake will fetch $($Target.hf_id)"
    } else {
        '(set -SourceDir or -HfId; Llama-3.1 must already be ReLU)'
    }
    @"
PowerInfer native Windows pipeline
  model_id           : $ModelId
  route              : $($Target.route)
  class              : $($Target.class)
  hidden/ff/layers   : $($Target.hidden_size) / $($Target.intermediate_size) / $($Target.num_hidden_layers)
  vocabtype          : $($Target.vocabtype)
  requires_relufy    : $($Target.requires_relufication)
  source             : $resolvedSource
  vault/bundle       : $Bundle
  PowerInfer tree    : $PowerInferDir
  CUDA combo         : VS 2022 x64 DevCmd + Ninja, -DLLAMA_CUBLAS=ON, CMAKE_CUDA_ARCHITECTURES=$CudaArch (CUDA 12.8+)
  native source/build: $NativeSourceDir / $NativeBuildDir (short paths; override with POWERINFER_NATIVE_SOURCE/BUILD)
  server bind        : $($Defaults.server_host):$($Defaults.server_port)  (native 127.0.0.1, not WSL2)
  vram-budget        : $(if ($null -eq $VramBudget) { '(not set -- required before validate/bench)' } else { $VramBudget })
  train plan          : layers $LayerStart..$($LayerStart + $EffectiveLayerCount - 1), samples=$EffectiveTrainSamples, rank=$EffectivePredictorRank, batch=$EffectiveTrainBatchSize, epochs=$EffectiveTrainEpochs
  execute            : $Execute

Stages (same dump/train/convert for both models):
  setup      clone+venv+pip+cmake CUDA build
  intake     huggingface download into bundle/source/hf (hashed, not edited)
  relu-gate  fail closed unless hidden_act=relu and shapes match
  calib      C4 JSONL calibration manifest
  dump       predictor mmaps + activation/activation_L.pt
  train      per-layer fc1/fc2 predictors
  convert    convert.py --outtype f16  (bpe for llama31)
  quantize   quantize.exe Q4_0
  package    copy activation next to GGUF + manifest.json
  validate   main.exe smoke; parse CUDA/solver/FFN-split logs
  bench      cold+warm $($Defaults.bench_turns)-turn acceptance_gate.json
"@ | Write-Host
}

function Resolve-NativeSourceAlias {
    if (Test-Path -LiteralPath $NativeSourceDir) {
        $item = Get-Item -LiteralPath $NativeSourceDir -Force
        if (-not ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
            throw "native source alias exists but is not a junction: $NativeSourceDir. Refusing to replace it."
        }
        return
    }
    New-Item -ItemType Junction -Path $NativeSourceDir -Target $PowerInferDir | Out-Null
}

function Invoke-DeveloperCommand([string]$CommandLine) {
    & cmd.exe /d /s /c "call `"$($script:Toolchain.VsDevCmdPath)`" -arch=x64 -host_arch=x64 && $CommandLine"
    if ($LASTEXITCODE -ne 0) { throw "developer-shell command failed: $CommandLine" }
}

function Invoke-Setup {
    Assert-Execute $false
    $toolchain = Resolve-NativeToolchain
    New-Item -ItemType Directory -Force -Path $External | Out-Null
    if (-not (Test-Path $PowerInferDir)) {
        git clone https://github.com/Tiiny-AI/PowerInfer.git $PowerInferDir
    }
    Resolve-NativeSourceAlias
    New-Item -ItemType Directory -Force -Path $NativeBuildDir | Out-Null
    $venv = Join-Path $PowerInferDir '.venv'
    if (-not (Test-Path (Join-Path $venv 'Scripts\python.exe'))) {
        py -3 -m venv $venv
    }
    $script:Py = Join-Path $venv 'Scripts\python.exe'
    & $Py -m pip install --upgrade pip
    # Upstream lists local bundled projects as bare ``./gguf-py`` and
    # ``./powerinfer-py`` lines. Recent pip treats that syntax as an invalid
    # requirement rather than an install target, so install the two local
    # projects explicitly and retain the upstream pinned runtime dependencies.
    & $Py -m pip install 'numpy>=1.24.4' 'sentencepiece>=0.1.98' 'transformers>=4.33.2'
    if ($LASTEXITCODE -ne 0) { throw 'PowerInfer base Python dependencies failed to install' }
    & $Py -m pip install (Join-Path $PowerInferDir 'gguf-py') (Join-Path $PowerInferDir 'powerinfer-py')
    if ($LASTEXITCODE -ne 0) { throw 'PowerInfer bundled Python projects failed to install' }
    & $Py -m pip install torch --index-url https://download.pytorch.org/whl/cu128
    if ($LASTEXITCODE -ne 0) { throw 'CUDA 12.8 PyTorch failed to install' }
    # ReLU Llama's SentencePiece tokenizer requires protobuf; current
    # Transformers may attempt the TikToken converter as a fallback. Install
    # both explicitly so the activation dump fails neither before loading
    # weights nor after a partial artifact write.
    & $Py -m pip install datasets jsonlines tqdm safetensors accelerate bitsandbytes cvxopt==1.3.2 huggingface_hub protobuf tiktoken
    if ($LASTEXITCODE -ne 0) { throw 'PowerInfer helper dependencies failed to install' }
    # The CUDA 12.8 PyTorch wheel needs the matching toolkit DLL directory on
    # PATH. Do not create a second case-variant `PATH` variable here: VS 2026
    # MSBuild rejects an environment containing both `Path` and `PATH`.
    $nvccVersion = & $toolchain.NvccPath --version | Out-String
    Write-Host "nvcc: $($nvccVersion.Trim())"
    $script:Toolchain = $toolchain
    $VisualStudioGenerator = $toolchain.Generator
    $cmakePath = $toolchain.CmakePath
    $cudaRoot = Split-Path -Parent (Split-Path -Parent $toolchain.NvccPath)
    $cudaRuntime = Join-Path $cudaRoot 'lib\x64\cudart.lib'
    if (-not (Test-Path -LiteralPath $cudaRuntime)) {
        throw "CUDA runtime import library was not found: $cudaRuntime"
    }
    Write-Host "CMake: $cmakePath | generator: $VisualStudioGenerator"
    $configure = '"{0}" -S "{1}" -B "{2}" -G Ninja -DCMAKE_MAKE_PROGRAM="{3}" -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_COMPILER="{4}" -DLLAMA_CUBLAS=ON -DCMAKE_CUDA_ARCHITECTURES={5} -DCUDAToolkit_ROOT="{6}" -DCUDA_CUDART:FILEPATH="{7}"' -f $cmakePath,$NativeSourceDir,$NativeBuildDir,$toolchain.NinjaPath,$toolchain.NvccPath,$CudaArch,$cudaRoot,$cudaRuntime
    Invoke-DeveloperCommand $configure
    $build = '"{0}" --build "{1}" --parallel' -f $cmakePath,$NativeBuildDir
    Invoke-DeveloperCommand $build
    foreach ($bin in @($MainExe, $ServerExe, $QuantizeExe)) {
        if (-not (Test-Path $bin)) { throw "missing binary $bin" }
    }
}

function Invoke-Intake {
    Assert-Execute $false
    $id = if ($HfId) { $HfId } else { [string]$Target.hf_id }
    if (-not $id) {
        throw "$ModelId has no hf_id. Pass -HfId <repo> or -SourceDir <local ReLU checkpoint>."
    }
    $dest = Join-Path $Bundle 'source\hf'
    if ((Test-Path $dest) -and -not $Force) { throw "refusing to overwrite $dest (pass -Force)" }
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Invoke-Py (Join-Path $Tools 'download_source.py') --repo $id --dest $dest
}

function Invoke-ReluGate {
    $src = Get-Source $Target $Bundle
    if (-not $src) { throw 'no source checkpoint. Pass -SourceDir or run intake.' }
    Invoke-Py (Join-Path $Tools 'check_relu_gate.py') --model-id $ModelId --source $src
}

function Invoke-Calib {
    Assert-Execute $false
    $calib = Join-Path $Bundle 'calibration'
    if ((Test-Path (Join-Path $calib 'sparse_calib.jsonl')) -and -not $Force) {
        throw "calibration already exists at $calib"
    }
    Invoke-Py (Join-Path $Tools 'build_calib.py') --out $calib
}

function Invoke-Dump {
    Assert-Execute $true
    $src = Get-Source $Target $Bundle
    if (-not $src) { throw 'no source checkpoint' }
    Invoke-ReluGate
    if ($Target.requires_approved_calibration) {
        if (-not $ApprovedPairsPath) {
            throw 'this target requires -ApprovedPairsPath with at least 32 operator-approved contrastive pairs before any GPU dump/train work'
        }
        if (-not (Test-Path -LiteralPath $ApprovedPairsPath)) {
            throw "ApprovedPairsPath not found: $ApprovedPairsPath"
        }
        Invoke-Py (Join-Path $Tools 'validate_approved_calibration_pairs.py') $ApprovedPairsPath
        if ($Target.requires_approved_source_manifest) {
            $sourceManifest = Join-Path $src 'abliteration_manifest.json'
            if (-not (Test-Path -LiteralPath $sourceManifest)) {
                throw "this target requires an immutable ablation manifest built from the approved pairs: $sourceManifest"
            }
            $manifest = Get-Content -Raw -LiteralPath $sourceManifest | ConvertFrom-Json
            $gate = $manifest.calibration_gate
            if (-not $gate -or $gate.status -ne 'approved_input' -or [int]$manifest.pairs -lt 32) {
                throw 'source checkpoint was not rebuilt from >=32 approved pairs. The current 20260830b checkpoint is exploratory and cannot enter predictor generation. Re-run abliterate_turbosparse_v2.py into a new immutable directory first.'
            }
            $expectedPairHash = [string]$manifest.sha256.'calibration_pairs.jsonl'
            $actualPairHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ApprovedPairsPath).Hash.ToLowerInvariant()
            if (-not $expectedPairHash -or $actualPairHash -ne $expectedPairHash.ToLowerInvariant()) {
                throw 'approved pair file does not byte-match the pair file recorded in the immutable source manifest; refusing mismatched predictor lineage'
            }
        }
        $approvedDest = Join-Path $Bundle 'calibration\approved_pairs.jsonl'
        if (Test-Path -LiteralPath $approvedDest) {
            throw "approved calibration evidence already exists: $approvedDest"
        }
        Copy-Item -LiteralPath $ApprovedPairsPath -Destination $approvedDest -ErrorAction Stop
    }
    $jsonl = Join-Path $Bundle 'calibration\sparse_calib.jsonl'
    if (-not (Test-Path $jsonl)) { throw "run calib first: $jsonl" }
    $dumpArgs = @(
        (Join-Path $Tools 'dump_activations.py'),
        '--model', $src,
        '--jsonl', $jsonl,
        '--out', $Bundle,
        '--max-samples', $Defaults.max_samples,
        '--max-length', $Defaults.max_length,
        '--hidden-size', $Target.hidden_size,
        '--intermediate-size', $Target.intermediate_size,
        '--num-hidden-layers', $Target.num_hidden_layers,
        '--expected-act', $Target.expected_hidden_act,
        '--solver-batch', $Defaults.solver_batch
    )
    if ($Load4Bit) { $dumpArgs += '--load-4bit' }
    if ($Target.trust_remote_code) { $dumpArgs += '--trust-remote-code' }
    Invoke-Py @dumpArgs
}

function Invoke-Train {
    Assert-Execute $true
    $predData = Join-Path $Bundle 'predictor_data'
    $workspace = if ($PredictorWorkspace) { $PredictorWorkspace } else { $Bundle }
    $predOut = Join-Path $workspace 'predictor_raw'
    New-Item -ItemType Directory -Force -Path $predOut | Out-Null
    $LayerStart..($LayerStart + $EffectiveLayerCount - 1) | ForEach-Object {
        Invoke-Py @(
            (Join-Path $Tools 'train_predictor_layer.py'),
            '--dataset', $predData,
            '--out', $predOut,
            '--L', "$_",
            '--hidden-size', $Target.hidden_size,
            '--intermediate-size', $Target.intermediate_size,
            '--N', $EffectiveTrainSamples,
            '--D', $EffectivePredictorRank,
            '--batch-size', $EffectiveTrainBatchSize,
            '--epochs', $EffectiveTrainEpochs,
            '--lr', $Defaults.train_lr
        )
    }
    $missing = @(0..($Target.num_hidden_layers - 1) | Where-Object {
        -not (Test-Path -LiteralPath (Join-Path $predOut "model_$_.pt"))
    })
    if ($missing.Count -gt 0) {
        Write-Host "predictor assembly deferred: $($missing.Count) of $($Target.num_hidden_layers) layer checkpoints are still missing" -ForegroundColor Yellow
        return
    }
    Invoke-Py @(
        (Join-Path $Tools 'assemble_predictor.py'),
        '--src', $predOut,
        '--dst', (Join-Path $workspace 'predictor'),
        '--layers', $Target.num_hidden_layers,
        '--sparse-threshold', $Defaults.sparse_threshold
    )
}

function Invoke-Convert {
    Assert-Execute $false
    $src = Get-Source $Target $Bundle
    $workspace = if ($PredictorWorkspace) { $PredictorWorkspace } else { $Bundle }
    $pred = Join-Path $workspace 'predictor'
    $outDir = Join-Path $ArtifactRoot 'output'
    New-Item -ItemType Directory -Force -Path $outDir | Out-Null
    if ((Test-Path $Gguf) -and -not $Force) { throw "exists $Gguf" }
    $convert = Join-Path $PowerInferDir 'convert.py'
    $convertArgs = @(
        $convert, '--outfile', $Gguf, '--outtype', [string]$Defaults.outtype
    )
    if ($VocabArgs.Count -gt 0) { $convertArgs += $VocabArgs }
    $convertArgs += @($src, $pred)
    Push-Location $PowerInferDir
    try {
        Invoke-Py @convertArgs
    } finally {
        Pop-Location
    }
}

function Invoke-Quantize {
    Assert-Execute $false
    if (-not (Test-Path $QuantizeExe)) { throw "missing $QuantizeExe; run setup" }
    if ((Test-Path $Q4) -and -not $Force) { throw "exists $Q4" }
    & $QuantizeExe $Gguf $Q4 $Defaults.quant
    if ($LASTEXITCODE -ne 0) { throw 'quantize failed' }
}

function Invoke-Package {
    $actSrc = Join-Path $Bundle 'activation'
    $actDst = Join-Path $ArtifactRoot 'output\activation'
    New-Item -ItemType Directory -Force -Path $actDst | Out-Null
    Copy-Item (Join-Path $actSrc 'activation_*.pt') $actDst -Force
    $commit = ''
    if (Test-Path (Join-Path $PowerInferDir '.git')) {
        # Git may correctly reject a repository owned by the interactive
        # Windows account when this runner is invoked from a sandbox account.
        # Commit provenance is useful but not required to package a candidate;
        # never mutate the user's global safe.directory list from this runner.
        $commitResult = @(git -C $PowerInferDir rev-parse HEAD 2>$null)
        if ($LASTEXITCODE -eq 0 -and $commitResult.Count -gt 0) {
            $commit = $commitResult[0].ToString().Trim()
        }
    }
    $src = Get-Source $Target $Bundle
    Invoke-Py @(
        (Join-Path $Tools 'write_manifest.py'),
        '--bundle', $ArtifactRoot,
        '--model-id', $ModelId,
        '--build-id', $Bid,
        '--source', $src,
        '--calibration-path', (Join-Path $Bundle 'calibration\calibration_manifest.json'),
        '--activation-dir', $actSrc,
        '--predictor-dir', (Join-Path $ArtifactRoot 'predictor'),
        '--status', 'candidate',
        '--powerinfer-commit', $commit
    )
    Write-Host "candidate artifacts ready: $ArtifactRoot"
    Write-Host "place runtime next to GGUF: $actDst"
}

function Invoke-ValidateAndBench([switch]$Bench) {
    Assert-Execute $true
    if ($null -eq $VramBudget) {
        throw "Pass -VramBudget <GiB> explicitly -- no silent default reaches the GPU binary. " +
              "Check the GPU gateway/idle status and confirm ComfyUI isn't holding the card first, " +
              "then pick a budget below whatever the gateway reports as free."
    }
    $modelPath = if (Test-Path $Q4) { $Q4 } else { $Gguf }
    $runtimeDir = Split-Path $modelPath -Parent
    $actLive = Join-Path $runtimeDir 'activation'
    if (-not (Test-Path $actLive)) {
        New-Item -ItemType Directory -Force -Path $actLive | Out-Null
        Copy-Item (Join-Path $Bundle 'activation\activation_*.pt') $actLive -Force
    }
    if ($Bench) {
        $benchArgs = @(
            (Join-Path $Tools 'record_acceptance_gate.py'),
            '--bundle', $ArtifactRoot,
            '--model-id', $ModelId,
            '--main-exe', $MainExe,
            '--server-exe', $ServerExe,
            '--gguf', $modelPath,
            '--host', $Defaults.server_host,
            '--port', $Defaults.server_port,
            '--vram-budget', "$VramBudget",
            '--threads', "$Threads",
            '--context', $Defaults.context,
            '--turns', $Defaults.bench_turns,
            '--max-tokens', $Defaults.bench_max_tokens
        )
        if ($SkipGpuPreflight) { $benchArgs += '--skip-gpu-preflight' }
        Invoke-Py @benchArgs
    } else {
        $stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
        $log = Join-Path $ArtifactRoot ("validation\main_smoke_$stamp.log")
        New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
        # Start-Process flattens a multi-word prompt into separate arguments on
        # Windows. Use native argument splatting so the smoke prompt remains one
        # value, and keep one bounded combined log rather than teeing a log back
        # into itself.
        $mainArgs = @(
            '-m', $modelPath, '-n', '16', '-t', "$Threads",
            '--vram-budget', "$VramBudget", '-p', 'Once upon a time'
        )
        # PowerInfer's native loader invokes the literal `python -m powerinfer`
        # while building its FFN split. Scope PATH to the repository venv so that
        # child process uses the installed matching package, never the unrelated
        # system Python. Restore the caller environment immediately afterwards.
        $priorPath = $env:Path
        $priorPythonPath = $env:PYTHONPATH
        try {
            $env:Path = (Join-Path $PowerInferDir '.venv\Scripts') + ';' + $priorPath
            $env:PYTHONPATH = $Tools + ';' + $PowerInferDir
            & $MainExe @mainArgs *> $log
            $mainExit = $LASTEXITCODE
        } finally {
            $env:Path = $priorPath
            $env:PYTHONPATH = $priorPythonPath
        }
        $flags = Join-Path $ArtifactRoot ("validation\split_flags_$stamp.json")
        Invoke-Py -c "from pathlib import Path; from pipeline_lib import parse_powerinfer_logs, write_json; t=Path(r'$log').read_text(encoding='utf-8', errors='replace'); write_json(Path(r'$flags'), parse_powerinfer_logs(t))"
        if ($mainExit -ne 0) { throw "main.exe failed: $mainExit (see $log)" }
    }
}

Show-Plan
if ($Stage -eq 'show') { return }

Invoke-VaultInit

$all = @(
    'setup', 'intake', 'relu-gate', 'calib', 'dump', 'train',
    'convert', 'quantize', 'package', 'validate', 'bench'
)
$todo = if ($Stage -eq 'all') { $all } else { @($Stage) }
if ($ModelId -eq 'llama31-8b-abliterated-relu' -and $todo -contains 'intake' -and -not $SourceDir -and -not $HfId -and -not $Target.hf_id) {
    Write-Warning 'Skipping intake: Llama-3.1 target needs a ReLU checkpoint via -SourceDir. SiLU abliterated weights will fail relu-gate.'
    $todo = @($todo | Where-Object { $_ -ne 'intake' })
}

foreach ($step in $todo) {
    Write-Host "==== $step ====" -ForegroundColor Cyan
    switch ($step) {
        'setup' { Invoke-Setup }
        'intake' { Invoke-Intake }
        'relu-gate' { Invoke-ReluGate }
        'calib' { Invoke-Calib }
        'dump' { Invoke-Dump }
        'train' { Invoke-Train }
        'convert' { Invoke-Convert }
        'quantize' { Invoke-Quantize }
        'package' { Invoke-Package }
        'validate' { Invoke-ValidateAndBench }
        'bench' { Invoke-ValidateAndBench -Bench }
    }
}
