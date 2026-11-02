# Installs or updates image-blaster into tools\image-blaster (Windows PowerShell).
# Usage (from the LocalAIproject folder):
#   powershell -ExecutionPolicy Bypass -File scripts\setup-image-blaster.ps1
$ErrorActionPreference = "Stop"

$RepoUrl = "https://github.com/neilsonnn/image-blaster"
$Root = Split-Path -Parent $PSScriptRoot
$Dest = Join-Path $Root "tools\image-blaster"

$tools = [ordered]@{
  "git"    = "install from https://git-scm.com/download/win (Claude Code on Windows also needs Git Bash)"
  "node"   = "install Node.js 18+ LTS from https://nodejs.org"
  "bun"    = "install with: powershell -c `"irm bun.sh/install.ps1 | iex`""
  "claude" = "install with: irm https://claude.ai/install.ps1 | iex"
}
$missing = $false
foreach ($name in $tools.Keys) {
  if (Get-Command $name -ErrorAction SilentlyContinue) {
    $ver = (& $name --version 2>$null | Select-Object -First 1)
    Write-Host "ok: $name ($ver)"
  } else {
    Write-Host "MISSING: $name -- $($tools[$name])" -ForegroundColor Yellow
    $missing = $true
  }
}
if ($missing) {
  Write-Host "`nInstall the missing tools above, open a NEW PowerShell window, and run this script again."
  exit 1
}

$nodeMajor = [int](node -p "process.versions.node.split('.')[0]")
if ($nodeMajor -lt 18) {
  Write-Host "Node $nodeMajor is too old; image-blaster needs Node 18+." -ForegroundColor Red
  exit 1
}

if (Test-Path (Join-Path $Dest ".git")) {
  Write-Host "Updating existing image-blaster in $Dest"
  git -C $Dest pull --ff-only
} else {
  Write-Host "Cloning image-blaster into $Dest"
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Dest) | Out-Null
  # Keep LF line endings so the bash hooks run correctly under Git Bash.
  git clone --config core.autocrlf=false --config core.eol=lf $RepoUrl $Dest
}

Set-Location $Dest
New-Item -ItemType Directory -Force -Path "input", "worlds" | Out-Null

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created $Dest\.env -- open it and paste your API keys."
}

Write-Host "Installing viewer dependencies (bun install)..."
bun install

Write-Host "`nDone. Next:"
Write-Host "  1. Put your keys in $Dest\.env  (WORLD_LABS_API_KEY, FAL_KEY)"
Write-Host "  2. cd `"$Dest`"; claude"
Write-Host "  3. Drop an image in input\ and say: blast it and confirm each step with me"
