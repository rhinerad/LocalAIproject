<#
.SYNOPSIS
  Pull the latest cloud (Claude) edits from GitHub into the local project.
.DESCRIPTION
  Fetches all remote branches, then pulls into the current branch (or switches to
  -Branch first). Refuses to run if you have uncommitted changes unless -Stash is used.
.EXAMPLE
  .\sync_down.ps1                                   # pull current branch
  .\sync_down.ps1 -Branch claude/zealous-johnson-g4xoz1
  .\sync_down.ps1 -Latest                           # switch to newest claude/* branch
#>
param(
    [string]$Branch,
    [switch]$Latest,
    [switch]$Stash
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = 'A:\Users\rhine\Documents\Codex\2026-08-07\referenced-chatgpt-conversation-this-is-an-2\COMFYUI_STORY_HANDOFF_2026-08-09'
if (-not (Test-Path $ProjectRoot)) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }
Set-Location $ProjectRoot

function Pause-IfDoubleClicked {
    if ($Host.Name -eq 'ConsoleHost' -and -not $env:WT_SESSION_KEEP) { Read-Host 'Press Enter to close' | Out-Null }
}

try {
    Write-Host "==> Project: $ProjectRoot" -ForegroundColor Cyan
    git fetch --all --prune
    if ($LASTEXITCODE) { throw 'git fetch failed' }

    if ($Latest) {
        $Branch = git for-each-ref --sort=-committerdate --format='%(refname:lstrip=3)' 'refs/remotes/origin/claude/' |
                  Select-Object -First 1
        if (-not $Branch) { throw 'No claude/* branches found on origin.' }
        Write-Host "==> Newest cloud branch: $Branch" -ForegroundColor Cyan
    }

    $dirty = git status --porcelain
    if ($dirty) {
        if ($Stash) {
            git stash push -u -m "sync_down autostash $(Get-Date -Format s)"
            $stashed = $true
        } else {
            git status --short
            throw 'You have uncommitted local changes. Run sync_up.ps1 first, or re-run with -Stash.'
        }
    }

    if ($Branch) {
        git switch $Branch 2>$null
        if ($LASTEXITCODE) { git switch -c $Branch --track "origin/$Branch" }
        if ($LASTEXITCODE) { throw "Could not switch to $Branch" }
    }

    $current = git rev-parse --abbrev-ref HEAD
    Write-Host "==> Pulling origin/$current" -ForegroundColor Cyan
    git pull --ff-only origin $current
    if ($LASTEXITCODE) { throw 'Pull failed (branches diverged?). Resolve manually: git pull --rebase' }

    if ($stashed) { git stash pop }

    Write-Host "`n==> Up to date. Recent commits:" -ForegroundColor Green
    git log --oneline -5
    Write-Host "`nOther cloud branches (newest first):" -ForegroundColor DarkGray
    git for-each-ref --sort=-committerdate --count=5 --format='  %(refname:lstrip=3)  (%(committerdate:relative))' 'refs/remotes/origin/claude/'
} catch {
    Write-Host "ERROR: $_" -ForegroundColor Red
    Pause-IfDoubleClicked
    exit 1
}
Pause-IfDoubleClicked
