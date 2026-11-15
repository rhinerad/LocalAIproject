<#
.SYNOPSIS
  Stop tracking private local data in git WITHOUT deleting it from disk.
.DESCRIPTION
  The 2026-11 audit found the assistant's chat memory, uploads, render jobs,
  logs and a few local-only files committed to GitHub. They are now listed in
  .gitignore, but git keeps tracking files that were already committed, and a
  commit that deletes them would also delete them from this working tree on
  the next pull. So the untracking happens HERE, on the machine that owns the
  files: `git rm --cached` removes them from the index only; the files stay
  exactly where they are and are ignored from then on.

  Run once from the project root after pulling the remediation branch:
      .\scripts\untrack_private_data.ps1          # untrack + commit
      .\scripts\untrack_private_data.ps1 -NoCommit
  Then run sync_up.ps1 (or push) as usual.

  This does NOT rewrite history: the old copies remain in previous commits on
  GitHub. See AUDIT_2026-11-02.md §6 step 1 for the history-rewrite procedure.
#>
param([switch]$NoCommit)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$paths = @(
    'local_agent/chats',
    'local_agent/uploads',
    'local_agent/render_jobs',
    'local_agent/rns_wifi/storage',
    'local_agent/tests/rns_offline/storage',
    'logs',
    'ARCHIVE_DECISION.md',
    'SYNC_STATUS.json',
    'SYNC_LOG.txt',
    'pasted-text.txt',
    '_agent_diff.txt',
    '.claude/settings.local.json',
    '.claude/launch.json',
    'CHANGELOG/.id_claims',
    'CHANGELOG/.next_changelog_id.lock'
)

$removed = 0
foreach ($p in $paths) {
    $tracked = git ls-files -- $p
    if ($tracked) {
        git rm -r -q --cached -- $p
        if ($LASTEXITCODE) { throw "git rm --cached failed for $p" }
        $n = ($tracked | Measure-Object).Count
        Write-Host "  untracked $p ($n files, left on disk)" -ForegroundColor Yellow
        $removed += $n
    }
}
# Every tracked log anywhere in the tree.
$logs = git ls-files -- '*.log' '*.err' '*.log.*' | Where-Object { $_ }
if ($logs) {
    $logs | ForEach-Object { git rm -q --cached -- $_ }
    Write-Host "  untracked $(($logs | Measure-Object).Count) log files (left on disk)" -ForegroundColor Yellow
    $removed += ($logs | Measure-Object).Count
}

if ($removed -eq 0) { Write-Host '==> Nothing left to untrack.' -ForegroundColor Green; exit 0 }
if ($NoCommit) { Write-Host "==> $removed files untracked and staged; commit when ready." -ForegroundColor Cyan; exit 0 }
git commit -q -m "Untrack private local data and logs (kept on disk; now gitignored)"
if ($LASTEXITCODE) { throw 'git commit failed' }
Write-Host "==> Committed: $removed files untracked. Files remain on disk." -ForegroundColor Green
