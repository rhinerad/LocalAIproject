$ErrorActionPreference = 'Stop'

# This is intentionally a fixed, single-use approved smoke invocation.  Passing
# the prompt through PowerShell's call operator keeps it one argument on Windows.
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$stdout = Join-Path $repoRoot 'work\runtime\image_render_smoke_20260825_r4\stdout.log'
$stderr = Join-Path $repoRoot 'work\runtime\image_render_smoke_20260825_r4\stderr.log'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $stdout) | Out-Null

& $python (Join-Path $repoRoot 'work\image_render.py') `
    --story 'realvisxl-smoke' `
    --prompt 'cinematic photoreal portrait of an adult woman seated by a large window in a warm sunlit apartment, natural skin texture, 50mm lens, shallow depth of field, candid editorial photograph' `
    --model 'RealVisXL_V5.0_fp16.safetensors' `
    --seed '20260825' `
    --width '1024' `
    --height '1024' `
    --steps '28' `
    --cfg '6' `
    --sampler 'dpmpp_2m_sde' `
    --scheduler 'karras' `
    --denoise '1.0' `
    --execute `
    --allow-model-load 1>> $stdout 2>> $stderr
exit $LASTEXITCODE
