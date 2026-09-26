<#
.SYNOPSIS
  Stage, commit (timestamped) and push local tweaks + debug output to GitHub.
.EXAMPLE
  .\sync_up.ps1
  .\sync_up.ps1 -Message "tweaked sampler steps"
#>
param([string]$Message)

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09'
if (-not (Test-Path $ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
Set-Location $ProjectRoot

function Pause-IfDoubleClicked {
    if ($Host.Name -eq 'ConsoleHost') { Read-Host 'Press Enter to close' | Out-Null }
}

try {
    $branch = git rev-parse --abbrev-ref HEAD
    Write-Host "==> Project: $ProjectRoot  [branch: $branch]" -ForegroundColor Cyan

    git add -A
    $staged = git diff --cached --name-only
    if (-not $staged) {
        Write-Host '==> Nothing to commit.' -ForegroundColor Yellow
    } else {
        # Warn about big files (GitHub rejects >100 MB; models/renders belong in .gitignore)
        foreach ($f in $staged) {
            if ((Test-Path $f) -and ((Get-Item $f).Length -gt 50MB)) {
                git reset -q -- $f
                Write-Host "  skipped large file (>50MB): $f  -- add it to .gitignore" -ForegroundColor Yellow
            }
        }
        if (-not $Message) { $Message = "Local sync $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') from $env:COMPUTERNAME" }
        git commit -m $Message
        if ($LASTEXITCODE) { throw 'git commit failed' }
    }

    # Pick up any cloud edits on this branch before pushing
    git pull --rebase --autostash origin $branch 2>$null
    git push -u origin $branch
    if ($LASTEXITCODE) { throw 'git push failed' }

    Write-Host "`n==> Pushed to origin/$branch" -ForegroundColor Green
    git log --oneline -3
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Pause-IfDoubleClicked
    exit 1
}
Pause-IfDoubleClicked
