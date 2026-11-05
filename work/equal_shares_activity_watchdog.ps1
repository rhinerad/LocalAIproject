$ErrorActionPreference = 'Continue'
$Project = Split-Path -Parent $PSScriptRoot
$Runtime = Join-Path $Project 'outputs\equal_shares\runtime'
$Owner = Join-Path $Runtime 'activity_watchdog_owner.json'
$StatePath = Join-Path $Runtime 'activity_watchdog_state.json'
$Log = Join-Path $Runtime 'activity_watchdog.log'
$ClaudeLauncher = Join-Path $PSScriptRoot 'launch_claude_watch.ps1'
$HumanGate = Join-Path $Runtime 'human_decision_required.json'
$CheckSeconds = 300
$IdleMinutes = 20
$ClaudeCooldownMinutes = 45

function Test-LivePid([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    try {
        $Record = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        $OwnerPid = [int]$Record.pid
        return $OwnerPid -gt 0 -and $null -ne (Get-Process -Id $OwnerPid -ErrorAction SilentlyContinue)
    }
    catch { return $false }
}

function Write-WatchLog([string]$Message) {
    "[$(Get-Date -Format o)] $Message" | Add-Content -LiteralPath $Log -Encoding UTF8
}

function Write-Owner([int]$OwnerPid, [string]$Purpose) {
    @{ pid = $OwnerPid; updated_at = (Get-Date -Format o); purpose = $Purpose } |
        ConvertTo-Json | Set-Content -LiteralPath $Owner -Encoding UTF8
}

New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
Write-Owner -OwnerPid $PID -Purpose 'Equal Shares layered activity watchdog'
Write-WatchLog "watchdog started pid=$PID"

try {
    while ($true) {
        Write-Owner -OwnerPid $PID -Purpose 'Equal Shares layered activity watchdog'

        $ActiveOwners = @(
            'local_agent_owner.json',
            'omni_pipeline_owner.json',
            'render_queue_owner.json',
            'claude_watch_owner.json'
        ) | ForEach-Object { Join-Path $Runtime $_ } | Where-Object { Test-LivePid $_ }

        if ($ActiveOwners.Count -gt 0) {
            Start-Sleep -Seconds $CheckSeconds
            continue
        }

        if (Test-Path -LiteralPath $HumanGate) {
            Write-WatchLog 'all machine work reached an explicit human decision gate; no duplicate agent launched'
            Start-Sleep -Seconds $CheckSeconds
            continue
        }

        $ProgressFiles = @(
            'omni_pipeline_supervisor.log',
            'vox_reference_supervisor.log',
            'audio_pass_supervisor.log',
            'omni_voice_lock_test_receipt.json',
            'audio_pass_manifest.json'
        ) | ForEach-Object { Join-Path $Runtime $_ }
        $ProgressFiles += Join-Path $Project 'outputs\equal_shares\audio_pass_manifest.json'
        $Latest = $ProgressFiles | Where-Object { Test-Path -LiteralPath $_ } |
            ForEach-Object { (Get-Item -LiteralPath $_).LastWriteTime } |
            Sort-Object -Descending | Select-Object -First 1
        if ($Latest -and ((Get-Date) - $Latest).TotalMinutes -lt $IdleMinutes) {
            Start-Sleep -Seconds $CheckSeconds
            continue
        }

        $State = if (Test-Path -LiteralPath $StatePath) {
            Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        } else { $null }
        $LastClaude = if ($State -and $State.last_claude_launch) {
            [datetime]$State.last_claude_launch
        } else { [datetime]::MinValue }

        if (((Get-Date) - $LastClaude).TotalMinutes -ge $ClaudeCooldownMinutes) {
            Write-WatchLog 'no live worker and no meaningful progress; launching one Claude Code continuity watcher'
            Start-Process -FilePath 'powershell.exe' -ArgumentList @(
                '-NoLogo', '-ExecutionPolicy', 'Bypass', '-File', $ClaudeLauncher
            ) -WindowStyle Hidden
            @{ last_claude_launch = (Get-Date -Format o) } | ConvertTo-Json |
                Set-Content -LiteralPath $StatePath -Encoding UTF8
        }
        Start-Sleep -Seconds $CheckSeconds
    }
}
finally {
    Write-Owner -OwnerPid 0 -Purpose 'released'
    Write-WatchLog 'watchdog stopped'
}

