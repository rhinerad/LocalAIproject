<#
.SYNOPSIS
    Review, play and approve character voice reference samples.

.DESCRIPTION
    Wraps work/voice_manager.py with the one thing a CLI cannot do on its own:
    actually listening to the sample before approving it. Run from the folder
    containing outputs\ and work\.

.EXAMPLE
    .\work\voice_review.ps1 -Plan
    .\work\voice_review.ps1 -Extract
    .\work\voice_review.ps1 -Listen
    .\work\voice_review.ps1 -Listen -Character Narrator
    .\work\voice_review.ps1 -Approve Narrator
    .\work\voice_review.ps1 -ApproveAll
    .\work\voice_review.ps1 -Reroll Kent -Reason "too nasal"
    .\work\voice_review.ps1 -Gate
#>

[CmdletBinding()]
param(
    [switch]$Plan,
    [switch]$Extract,
    [switch]$Listen,
    [string]$Character,
    [string]$Approve,
    [switch]$ApproveAll,
    [string]$Reroll,
    [string]$Reason = "",
    [switch]$Gate
)

$ErrorActionPreference = "Stop"
$Py   = "A:\Users\rhine\ComfyUI-Installs\Rockernow\ComfyUI\.venv\Scripts\python.exe"
$Tool = Join-Path $PSScriptRoot "voice_manager.py"
$GateFile = "outputs\equal_shares\runtime\voice_approval_gate.json"

function Invoke-VoiceManager {
    param([string[]]$Arguments)
    & $Py $Tool @Arguments
    if ($LASTEXITCODE -ne 0 -and $Arguments[0] -ne "gate") {
        throw "voice_manager.py $($Arguments -join ' ') failed with $LASTEXITCODE"
    }
}

if ($Plan)      { Invoke-VoiceManager @("plan");    return }
if ($Extract)   {
    $a = @("extract")
    if ($Character) { $a += @("--character", $Character) } else { $a += "--all" }
    Invoke-VoiceManager $a
    return
}
if ($Gate)      { Invoke-VoiceManager @("gate");    return }
if ($ApproveAll){ Invoke-VoiceManager @("approve", "--all"); return }
if ($Approve)   { Invoke-VoiceManager @("approve", "--character", $Approve); return }
if ($Reroll)    { Invoke-VoiceManager @("reroll", "--character", $Reroll, "--reason", $Reason); return }

if ($Listen) {
    if (-not (Test-Path $GateFile)) { throw "no gate yet - run with -Plan then -Extract" }
    $gate = Get-Content $GateFile -Raw | ConvertFrom-Json

    $entries = $gate.characters.PSObject.Properties |
        Where-Object { -not $Character -or $_.Name -eq $Character } |
        ForEach-Object { $_.Value }

    foreach ($entry in $entries) {
        if (-not $entry.sample_seconds) {
            Write-Host ("{0,-24} no sample extracted yet" -f $entry.character) -ForegroundColor DarkGray
            continue
        }
        $path = $entry.sample_path -replace '/', '\'
        if (-not (Test-Path $path)) {
            Write-Host ("{0,-24} MISSING {1}" -f $entry.character, $path) -ForegroundColor Red
            continue
        }

        Write-Host ""
        Write-Host ("{0}  [{1}]  {2:N1}s  from {3}" -f `
            $entry.character, $entry.status, $entry.sample_seconds,
            ($entry.source_clips -join ", ")) -ForegroundColor Cyan
        Write-Host "  $path" -ForegroundColor DarkGray

        # Play it. SoundPlayer only handles PCM WAV, which is what we extract.
        try {
            $player = New-Object System.Media.SoundPlayer $path
            $player.PlaySync()
        } catch {
            Write-Host "  could not play - opening in the default handler" -ForegroundColor Yellow
            Start-Process $path
        }

        $answer = Read-Host "  [a]pprove  [r]e-roll  [s]kip  [q]uit"
        switch ($answer.ToLower()) {
            "a" { Invoke-VoiceManager @("approve", "--character", $entry.character) }
            "r" {
                $why = Read-Host "  reason"
                Invoke-VoiceManager @("reroll", "--character", $entry.character, "--reason", $why)
            }
            "q" { return }
            default { Write-Host "  skipped" -ForegroundColor DarkGray }
        }
    }

    Write-Host ""
    Invoke-VoiceManager @("gate")
    return
}

Write-Host "Nothing to do. Try -Plan, -Extract, -Listen, -ApproveAll or -Gate."
Get-Help $PSCommandPath -Examples
